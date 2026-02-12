"""
backend/etl.py

MSSQL -> Neo4j ETL for CyberFraud graph

Creates:
- (:Account) nodes for Victim and Accused accounts (single node type)
- One (:Account)-[:TRANSFERRED_TO]->(:Account) relationship PER TRANSFER EVENT
  using AARecID as unique transfer_id so multiple transfers between same accounts
  are preserved.

Source tables (MSSQL):
- dbo.Tbl_Fraud_VictimAccount
- dbo.Tbl_Fraud_AccusedAccount
- dbo.Tbl_Fraud_Bank (optional)

Key rules from your requirements:
- Nodes are Accounts (no separate Person node)
- Account node includes personal details from accused table (name, address, mobile, KYC etc.)
- Crime_No ties victims & accused to the case
- Money flow: ParentAccountNo -> AccusedAccountNo
- ParentAccountType = 'v' for first parent (Victim), 'c' otherwise
- AccusedAccountLevel indicates layer (for coloring/visualization)

Run:
  python etl.py

Prereqs:
  pip install pyodbc neo4j python-dotenv

Ensure config.py has correct MSSQL + Neo4j + creds.
"""

import os
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pyodbc
from neo4j import GraphDatabase
from dotenv import load_dotenv

# If you already have backend/config.py, keep using it.
# Otherwise set env vars and this script will read them.
try:
    from config import (
        MSSQL_SERVER,
        MSSQL_DATABASE,
        MSSQL_DRIVER,
        # add these to config.py (recommended):
        # MSSQL_UID, MSSQL_PWD,
        CHROMA_PATH,  # not used here, but safe if exists
    )
except Exception:
    MSSQL_SERVER = os.getenv("MSSQL_SERVER", "localhost")
    MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "CyberFraud")
    MSSQL_DRIVER = os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")

load_dotenv()

# ----------------------------
# MSSQL Credentials
# ----------------------------
MSSQL_UID = os.getenv("MSSQL_UID", "")
MSSQL_PWD = os.getenv("MSSQL_PWD", "")

# If using Windows Integrated Security, set:
#   MSSQL_TRUSTED_CONNECTION=1
MSSQL_TRUSTED_CONNECTION = os.getenv("MSSQL_TRUSTED_CONNECTION", "0")  # "1" or "0"

# ----------------------------
# Neo4j Credentials
# ----------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")

# ----------------------------
# ETL Tunables
# ----------------------------
BATCH_SIZE = int(os.getenv("ETL_BATCH_SIZE", "800"))
MAX_ROWS_VICTIM = int(os.getenv("ETL_MAX_VICTIM_ROWS", "0"))   # 0 = no limit
MAX_ROWS_ACCUSED = int(os.getenv("ETL_MAX_ACCUSED_ROWS", "0")) # 0 = no limit


# =============================================================================
# MSSQL helpers
# =============================================================================
def get_mssql_conn() -> pyodbc.Connection:
    """
    Supports:
    - SQL auth (MSSQL_UID/MSSQL_PWD)
    - Windows trusted connection if MSSQL_TRUSTED_CONNECTION=1
    """
    if MSSQL_TRUSTED_CONNECTION == "1":
        conn_str = (
            f"DRIVER={{{MSSQL_DRIVER}}};"
            f"SERVER={MSSQL_SERVER};"
            f"DATABASE={MSSQL_DATABASE};"
            "Trusted_Connection=yes;"
            "TrustServerCertificate=yes;"
        )
    else:
        conn_str = (
            f"DRIVER={{{MSSQL_DRIVER}}};"
            f"SERVER={MSSQL_SERVER};"
            f"DATABASE={MSSQL_DATABASE};"
            f"UID={MSSQL_UID};"
            f"PWD={MSSQL_PWD};"
            "TrustServerCertificate=yes;"
        )

    return pyodbc.connect(conn_str)


def fetch_all_dict(cur: pyodbc.Cursor) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    out = []
    for r in rows:
        d = {}
        for i, c in enumerate(cols):
            d[c] = r[i]
        out.append(d)
    return out


def to_str(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None


def to_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(x)
    except Exception:
        return None


def to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        if isinstance(x, float):
            if math.isnan(x):
                return None
        return float(x)
    except Exception:
        return None


def split_batches(rows: List[Dict[str, Any]], batch_size: int) -> List[List[Dict[str, Any]]]:
    return [rows[i:i + batch_size] for i in range(0, len(rows), batch_size)]


# =============================================================================
# Neo4j Cypher
# =============================================================================

# Constraints / Indexes (Neo4j 5+ syntax)
CYPHER_CONSTRAINTS = [
    "CREATE CONSTRAINT account_no_unique IF NOT EXISTS FOR (a:Account) REQUIRE a.account_no IS UNIQUE",
    "CREATE INDEX crime_no_idx IF NOT EXISTS FOR (a:Account) ON (a.crime_no)",
    "CREATE INDEX victim_id_idx IF NOT EXISTS FOR (a:Account) ON (a.victim_id)",
    "CREATE INDEX unit_id_idx IF NOT EXISTS FOR (a:Account) ON (a.unit_id)",
    # Relationship uniqueness is done via MERGE on transfer_id, not via constraint
]

# Victim nodes
CYPHER_UPSERT_VICTIMS = """
UNWIND $rows AS row
MERGE (a:Account {account_no: row.account_no})
SET
  a.account_type = 'victim',
  a.victim_id = row.victim_id,
  a.crime_no = row.crime_no,
  a.unit_id = row.unit_id,
  a.name = row.victim_name,
  a.bank_name = row.victim_bank_detail,
  a.bank_branch = row.victim_bank_branch,
  a.amount_sent = row.amount_sent,
  a.source = 'Tbl_Fraud_VictimAccount'
"""

# Accused account nodes (includes personal details)
CYPHER_UPSERT_ACCUSED = """
UNWIND $rows AS row
MERGE (a:Account {account_no: row.account_no})
SET
  a.account_type = 'accused',
  a.victim_id = row.victim_id,
  a.crime_no = row.crime_no,
  a.unit_id = row.unit_id,
  a.parent_account_no = row.parent_account_no,
  a.parent_account_type = row.parent_account_type,
  a.accused_level = row.accused_level,

  a.name = row.accused_name,
  a.address = row.accused_address,
  a.mobile = row.accused_mobile,

  a.bank_name = row.accused_bank_name,
  a.bank_branch = row.accused_bank_branch,
  a.bank_ifsc = row.accused_bank_ifsc,

  a.account_open_date = row.account_open_date,
  a.account_closed_date = row.account_closed_date,

  a.transaction_count = row.transaction_count,
  a.upi_transaction_count = row.upi_transaction_count,

  a.kyc_document_type = row.kyc_document_type,
  a.kyc_document_no = row.kyc_document_no,
  a.address_in_kyc = row.address_in_kyc,

  a.associated_mobile = row.associated_mobile,
  a.introducer_details = row.introducer_details,
  a.address_of_caf_associated = row.address_of_caf_associated,
  a.mobile_of_caf_associated = row.mobile_of_caf_associated,
  a.address_in_kyc_for_sim = row.address_in_kyc_for_sim,

  a.contacted_victim_mobile = row.contacted_victim_mobile,
  a.caf_of_mobile = row.caf_of_mobile,
  a.contacted_victim_social = row.contacted_victim_social,

  a.effort_to_detect_level1 = row.effort_to_detect_level1,
  a.modus_operandi_means = row.modus_operandi_means,
  a.is_fraud_account_identified = row.is_fraud_account_identified,
  a.action_taken = row.action_taken,
  a.remarks = row.remarks,

  a.upi_id = row.upi_id,
  a.upi_type = row.upi_type,

  a.source = 'Tbl_Fraud_AccusedAccount'
"""

# Ensure any missing parent accounts exist (because parent may be an accused account or victim)
# Create minimal nodes so relationships can attach.
CYPHER_ENSURE_PARENTS = """
UNWIND $rows AS row
WITH row
WHERE row.parent_account_no IS NOT NULL AND row.parent_account_no <> ''
MERGE (p:Account {account_no: row.parent_account_no})
ON CREATE SET
  p.account_type = CASE WHEN row.parent_account_type = 'v' THEN 'victim' ELSE 'unknown' END,
  p.source = 'AUTO_CREATED_PARENT'
"""

# ✅ Relationship per transfer event: MERGE with transfer_id (AARecID) ONLY.
# Then SET all other properties (null safe).
CYPHER_UPSERT_RELATIONSHIPS = """
UNWIND $rows AS row
WITH row
WHERE row.transfer_id IS NOT NULL
  AND row.parent_account_no IS NOT NULL AND row.parent_account_no <> ''
  AND row.child_account_no IS NOT NULL AND row.child_account_no <> ''

MATCH (p:Account {account_no: row.parent_account_no})
MATCH (c:Account {account_no: row.child_account_no})

MERGE (p)-[r:TRANSFERRED_TO {transfer_id: row.transfer_id}]->(c)

SET
  r.crime_no = row.crime_no,
  r.victim_id = row.victim_id,
  r.unit_id = row.unit_id,

  r.parent_account_no = row.parent_account_no,
  r.child_account_no = row.child_account_no,
  r.parent_account_type = row.parent_account_type,

  r.accused_level = row.accused_level,

  r.amount = row.amount_received,
  r.flow_type = row.flow_type,

  r.flow_date = CASE
                  WHEN row.flow_date IS NULL THEN r.flow_date
                  ELSE row.flow_date
                END
"""


# =============================================================================
# Extract from MSSQL
# =============================================================================
def extract_victims(mssql: pyodbc.Connection) -> List[Dict[str, Any]]:
    sql = """
    SELECT
      Victim_ID,
      Crime_No,
      Unit_ID,
      Victim_Name,
      VictimAccountNo,
      VictimBankDetail,
      VictimBankBranch,
      amountSent
    FROM dbo.Tbl_Fraud_VictimAccount
    """
    if MAX_ROWS_VICTIM and MAX_ROWS_VICTIM > 0:
        sql = f"SELECT TOP {MAX_ROWS_VICTIM} * FROM ({sql}) AS X"

    cur = mssql.cursor()
    cur.execute(sql)
    rows = fetch_all_dict(cur)

    out = []
    for r in rows:
        out.append({
            "victim_id": to_int(r.get("Victim_ID")),
            "crime_no": to_str(r.get("Crime_No")),
            "unit_id": to_int(r.get("Unit_ID")),
            "victim_name": to_str(r.get("Victim_Name")),
            "account_no": to_str(r.get("VictimAccountNo")),
            "victim_bank_detail": to_str(r.get("VictimBankDetail")),
            "victim_bank_branch": to_str(r.get("VictimBankBranch")),
            "amount_sent": to_float(r.get("amountSent")),
        })
    return out


def extract_accused(mssql: pyodbc.Connection) -> List[Dict[str, Any]]:
    sql = """
    SELECT
      AARecID,
      Victim_ID,
      Crime_No,
      Unit_ID,
      ParentAccountNo,
      ParentAccountType,
      AccusedAccountLevel,
      AccusedName,
      AccusedAddress,
      AccusedMobileNo,
      AccusedAccountNo,
      AccusedBankName,
      AccusedBankBranch,
      AccusedBankIFSC,
      AccountOpenDate,
      AccountClosedDate,
      TransactionCount,
      UPITransctionCount,
      KYCDocumentType,
      KYCDocumentNo,
      AddressinKYC,
      AssociatedMblNo,
      IntroducerDetails,
      AddressofCAFAssociated,
      MobileNoofCAFAssociated,
      AddressinKYCForSIMCard,
      ContactedtoVictimMblNo,
      CAFofMblNo,
      ContactedVictimSocialMediaDetail,
      EfforttoDetectLavel_1,
      ModusOperandiMeans,
      IsFraudAccountIdentified,
      ActionTakenNProposed,
      Remarks,
      amountReceived,
      UpiID,
      UpiType,
      FlowDate,
      FlowType
    FROM dbo.Tbl_Fraud_AccusedAccount
    """
    if MAX_ROWS_ACCUSED and MAX_ROWS_ACCUSED > 0:
        sql = f"SELECT TOP {MAX_ROWS_ACCUSED} * FROM ({sql}) AS X"

    cur = mssql.cursor()
    cur.execute(sql)
    rows = fetch_all_dict(cur)

    out = []
    for r in rows:
        out.append({
            "transfer_id": to_int(r.get("AARecID")),  # ✅ unique rel per event
            "victim_id": to_int(r.get("Victim_ID")),
            "crime_no": to_str(r.get("Crime_No")),
            "unit_id": to_int(r.get("Unit_ID")),

            "parent_account_no": to_str(r.get("ParentAccountNo")),
            "parent_account_type": to_str(r.get("ParentAccountType")),  # 'v' or 'c'
            "accused_level": to_int(r.get("AccusedAccountLevel")),

            "accused_name": to_str(r.get("AccusedName")),
            "accused_address": to_str(r.get("AccusedAddress")),
            "accused_mobile": to_str(r.get("AccusedMobileNo")),

            "account_no": to_str(r.get("AccusedAccountNo")),  # accused node account no
            "accused_bank_name": to_str(r.get("AccusedBankName")),
            "accused_bank_branch": to_str(r.get("AccusedBankBranch")),
            "accused_bank_ifsc": to_str(r.get("AccusedBankIFSC")),

            "account_open_date": r.get("AccountOpenDate"),
            "account_closed_date": r.get("AccountClosedDate"),

            "transaction_count": to_int(r.get("TransactionCount")),
            "upi_transaction_count": to_int(r.get("UPITransctionCount")),

            "kyc_document_type": to_str(r.get("KYCDocumentType")),
            "kyc_document_no": to_str(r.get("KYCDocumentNo")),
            "address_in_kyc": to_str(r.get("AddressinKYC")),

            "associated_mobile": to_str(r.get("AssociatedMblNo")),
            "introducer_details": to_str(r.get("IntroducerDetails")),
            "address_of_caf_associated": to_str(r.get("AddressofCAFAssociated")),
            "mobile_of_caf_associated": to_str(r.get("MobileNoofCAFAssociated")),
            "address_in_kyc_for_sim": to_str(r.get("AddressinKYCForSIMCard")),

            "contacted_victim_mobile": to_str(r.get("ContactedtoVictimMblNo")),
            "caf_of_mobile": to_str(r.get("CAFofMblNo")),
            "contacted_victim_social": to_str(r.get("ContactedVictimSocialMediaDetail")),

            "effort_to_detect_level1": to_str(r.get("EfforttoDetectLavel_1")),
            "modus_operandi_means": to_str(r.get("ModusOperandiMeans")),
            "is_fraud_account_identified": to_str(r.get("IsFraudAccountIdentified")),
            "action_taken": to_str(r.get("ActionTakenNProposed")),
            "remarks": to_str(r.get("Remarks")),

            # relationship fields
            "child_account_no": to_str(r.get("AccusedAccountNo")),
            "amount_received": to_float(r.get("amountReceived")),
            "upi_id": to_str(r.get("UpiID")),
            "upi_type": to_str(r.get("UpiType")),
            "flow_date": r.get("FlowDate"),
            "flow_type": to_str(r.get("FlowType")),
        })
    return out


# =============================================================================
# Load into Neo4j
# =============================================================================
def apply_constraints(driver) -> None:
    with driver.session() as session:
        for c in CYPHER_CONSTRAINTS:
            session.run(c)


def load_victims(driver, victim_rows: List[Dict[str, Any]]) -> None:
    batches = split_batches(victim_rows, BATCH_SIZE)
    with driver.session() as session:
        for b in batches:
            session.run(CYPHER_UPSERT_VICTIMS, rows=b)


def load_accused(driver, accused_rows: List[Dict[str, Any]]) -> None:
    batches = split_batches(accused_rows, BATCH_SIZE)
    with driver.session() as session:
        for b in batches:
            session.run(CYPHER_UPSERT_ACCUSED, rows=b)


def ensure_parents(driver, accused_rows: List[Dict[str, Any]]) -> None:
    batches = split_batches(accused_rows, BATCH_SIZE)
    with driver.session() as session:
        for b in batches:
            session.run(CYPHER_ENSURE_PARENTS, rows=b)


def load_relationships(driver, accused_rows: List[Dict[str, Any]]) -> None:
    """
    Creates one relationship per transfer event using transfer_id = AARecID.
    Null-safe: transfer_id required; flow_date can be null (set safely).
    """
    batches = split_batches(accused_rows, BATCH_SIZE)
    with driver.session() as session:
        for b in batches:
            session.run(CYPHER_UPSERT_RELATIONSHIPS, rows=b)


# =============================================================================
# Main
# =============================================================================
def main():
    print("=== MSSQL -> Neo4j ETL (CyberFraud) ===")
    print(f"MSSQL: {MSSQL_SERVER} / {MSSQL_DATABASE}")
    print(f"Neo4j: {NEO4J_URI}")

    # MSSQL connect
    mssql = get_mssql_conn()

    # Neo4j connect
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        print("[1/6] Applying Neo4j constraints/indexes...")
        apply_constraints(driver)

        print("[2/6] Extracting Victim accounts from MSSQL...")
        victim_rows = extract_victims(mssql)
        print(f"Victim rows: {len(victim_rows)}")

        print("[3/6] Loading Victim accounts into Neo4j...")
        load_victims(driver, victim_rows)

        print("[4/6] Extracting Accused accounts + flows from MSSQL...")
        accused_rows = extract_accused(mssql)
        print(f"Accused rows: {len(accused_rows)}")

        print("[5/6] Loading Accused accounts into Neo4j...")
        load_accused(driver, accused_rows)

        print("[5.5/6] Ensuring any missing parent accounts exist...")
        ensure_parents(driver, accused_rows)

        print("[6/6] Creating TRANSFERRED_TO relationships (per transfer event)...")
        load_relationships(driver, accused_rows)

        print("✅ ETL completed successfully.")

    finally:
        try:
            mssql.close()
        except Exception:
            pass
        try:
            driver.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
