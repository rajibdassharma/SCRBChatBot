"""
NCRP MSSQL -> Neo4j ETL

Corrected Data Model:
  - AccountOrWalletId = PARENT account (source of funds)
    For Layer 1 rows, AccountOrWalletId is the Victim account (Layer 0)
  - AccountNo = the actual account at the given Layer
  - Each row directly defines one relationship:
      AccountOrWalletId -> AccountNo

Creates:
- (:Account) nodes from BOTH AccountOrWalletId and AccountNo columns
- One (:Account)-[:TRANSFERRED_TO]->(:Account) relationship PER ROW
  using TrailID as unique transfer_id

Target Neo4j database: default 'neo4j' database (Community Edition compatible)

Source table (MSSQL): dbo.MoneyTransferTo (database: NCRP)

Run:
  python neo4j_etl.py

Prereqs:
  pip install pyodbc neo4j python-dotenv
"""

import os
import math
from collections import defaultdict
from typing import Any, Dict, List, Optional

import pyodbc
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# ----------------------------
# MSSQL Config
# ----------------------------
MSSQL_SERVER = os.getenv("MSSQL_SERVER", "localhost")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "NCRP")
MSSQL_DRIVER = os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")

MSSQL_CONN_STR = (
    f"Driver={{{MSSQL_DRIVER}}};"
    f"Server={MSSQL_SERVER};"
    f"Database={MSSQL_DATABASE};"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

# ----------------------------
# Neo4j Config
# ----------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "sandy411")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# ----------------------------
# ETL Tunables
# ----------------------------
BATCH_SIZE = int(os.getenv("ETL_BATCH_SIZE", "800"))


# =============================================================================
# MSSQL helpers
# =============================================================================
def get_mssql_conn() -> pyodbc.Connection:
    return pyodbc.connect(MSSQL_CONN_STR)


def fetch_all_dict(cur: pyodbc.Cursor) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cur.description]
    return [{cols[i]: r[i] for i in range(len(cols))} for r in cur.fetchall()]


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
        if isinstance(x, float) and math.isnan(x):
            return None
        return float(x)
    except Exception:
        return None


def split_batches(rows: List, size: int) -> List[List]:
    return [rows[i:i + size] for i in range(0, len(rows), size)]


# =============================================================================
# Neo4j Cypher statements
# =============================================================================

# Constraints / Indexes (Neo4j 5+ syntax)
CYPHER_CONSTRAINTS = [
    "CREATE CONSTRAINT account_no_unique IF NOT EXISTS FOR (a:Account) REQUIRE a.account_no IS UNIQUE",
    "CREATE INDEX crime_no_idx IF NOT EXISTS FOR (a:Account) ON (a.crime_no)",
]

# Account nodes (one per unique account)
CYPHER_UPSERT_ACCOUNTS = """
UNWIND $rows AS row
MERGE (a:Account {account_no: row.account_no})
SET
  a.name           = row.name,
  a.level          = row.level,
  a.crime_no       = row.crime_no,
  a.account_type   = row.account_type,
  a.bank_name      = row.bank_name,
  a.bank_ifsc      = row.bank_ifsc,
  a.amount         = row.amount,
  a.disputed       = row.disputed,
  a.action_taken   = row.action_taken,
  a.remarks        = row.remarks,
  a.case_count     = row.case_count,
  a.source         = 'NCRP_MoneyTransferTo'
"""

# Relationship per transfer event: MERGE with transfer_id (TrailID).
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
  r.crime_no       = row.crime_no,
  r.amount         = row.amount,
  r.child_level    = row.child_level,
  r.transaction_date = CASE
                         WHEN row.transaction_date IS NULL THEN r.transaction_date
                         ELSE row.transaction_date
                       END
"""


# =============================================================================
# Extract from MSSQL
# =============================================================================
def extract_transfers(mssql: pyodbc.Connection) -> List[Dict[str, Any]]:
    """
    Extract rows from MoneyTransferTo.

    Corrected model:
      - AccountOrWalletId = parent account (source of transfer)
      - AccountNo = the account AT this Layer
      - For Layer 1 rows, AccountOrWalletId is the Victim (Layer 0) account
    """
    sql = """
    SELECT
        TrailID,
        AcknowledgementNo,
        AccountOrWalletId,
        TransactionUTR,
        BankFIs,
        Layer,
        AccountNo,
        IFSCCode,
        TransactionDate,
        TransactionAmount,
        DisputedAmount,
        ActionTakenByBank,
        Remarks
    FROM dbo.MoneyTransferTo
    ORDER BY AcknowledgementNo, Layer, TrailID
    """
    cur = mssql.cursor()
    cur.execute(sql)
    rows = fetch_all_dict(cur)
    print(f"  Raw rows from MSSQL: {len(rows)}")

    out = []
    for r in rows:
        ack = to_str(r.get("AcknowledgementNo"))
        wallet_id = to_str(r.get("AccountOrWalletId"))
        account_no = to_str(r.get("AccountNo"))
        if not ack or not account_no:
            continue

        layer = to_int(r.get("Layer")) or 1

        out.append({
            "trail_id": to_int(r.get("TrailID")),
            "crime_no": ack,
            # Parent account (source of transfer)
            "wallet_id": wallet_id,
            # This layer's account
            "account_no": account_no,
            "level": layer,
            "bank_name": to_str(r.get("BankFIs")),
            "bank_ifsc": to_str(r.get("IFSCCode")),
            "amount": to_float(r.get("TransactionAmount")),
            "disputed": to_float(r.get("DisputedAmount")),
            "action_taken": to_str(r.get("ActionTakenByBank")),
            "remarks": to_str(r.get("Remarks")),
            "transaction_date": r.get("TransactionDate"),
        })
    return out


# =============================================================================
# Build nodes from both columns
# =============================================================================
def build_all_nodes(transfer_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build unique Account nodes from BOTH columns:
      1. AccountNo (at its Layer) — the child account in each row
      2. AccountOrWalletId (at Layer-1) — the parent account
         For Layer 1 rows, this is the victim account at Layer 0

    case_count: number of distinct AcknowledgementNos the account appears in
    (counted across both columns).
    """
    # Track case counts across both columns
    account_cases: Dict[str, set] = defaultdict(set)
    for r in transfer_rows:
        # The child account (AccountNo) appears in this case
        account_cases[r["account_no"]].add(r["crime_no"])
        # The parent account (AccountOrWalletId) also appears in this case
        if r["wallet_id"]:
            account_cases[r["wallet_id"]].add(r["crime_no"])

    # Collect node data — first occurrence wins for properties
    nodes: Dict[str, Dict[str, Any]] = {}

    for r in transfer_rows:
        # 1) Child node: AccountNo at this Layer
        child_key = r["account_no"]
        if child_key not in nodes:
            nodes[child_key] = {
                "account_no": child_key,
                "name": child_key,
                "level": r["level"],
                "crime_no": r["crime_no"],
                "account_type": "child",
                "bank_name": r["bank_name"],
                "bank_ifsc": r["bank_ifsc"],
                "amount": r["amount"],
                "disputed": r["disputed"],
                "action_taken": r["action_taken"],
                "remarks": r["remarks"],
            }

        # 2) Parent node: AccountOrWalletId at Layer-1
        if r["wallet_id"]:
            parent_key = r["wallet_id"]
            parent_level = r["level"] - 1  # one layer above
            if parent_key not in nodes:
                # For Layer 1 rows, parent is at Layer 0 (victim)
                account_type = "victim" if parent_level == 0 else "child"
                nodes[parent_key] = {
                    "account_no": parent_key,
                    "name": parent_key if account_type != "victim" else r["crime_no"],
                    "level": parent_level,
                    "crime_no": r["crime_no"],
                    "account_type": account_type,
                    "bank_name": None,
                    "bank_ifsc": None,
                    "amount": None,
                    "disputed": None,
                    "action_taken": None,
                    "remarks": None,
                }

    # Attach case_count to each node
    result = list(nodes.values())
    for node in result:
        node["case_count"] = len(account_cases.get(node["account_no"], set()))

    return result


# =============================================================================
# Build relationships — each row is one direct edge
# =============================================================================
def build_relationships(transfer_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Each row directly defines one relationship:
      AccountOrWalletId (parent) -> AccountNo (child)

    No inference needed — the data explicitly specifies both ends.
    TrailID is used as unique transfer_id.
    """
    edges = []
    for r in transfer_rows:
        parent = r["wallet_id"]
        child = r["account_no"]

        if not parent or not child:
            continue
        if parent == child:
            continue

        edges.append({
            "transfer_id": r["trail_id"],
            "parent_account_no": parent,
            "child_account_no": child,
            "crime_no": r["crime_no"],
            "amount": r["amount"],
            "child_level": r["level"],
            "transaction_date": r.get("transaction_date"),
        })

    return edges


# =============================================================================
# Load into Neo4j
# =============================================================================
def cleanup_ncrp_data(driver) -> None:
    """Delete all existing NCRP nodes and relationships before fresh load."""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(
            "MATCH (a:Account) WHERE a.source = 'NCRP_MoneyTransferTo' "
            "DETACH DELETE a RETURN count(a) AS deleted"
        )
        deleted = result.single()["deleted"]
        print(f"  Deleted {deleted} existing NCRP nodes (and their relationships).")


def apply_constraints(driver) -> None:
    with driver.session(database=NEO4J_DATABASE) as session:
        for c in CYPHER_CONSTRAINTS:
            try:
                session.run(c)
            except Exception as e:
                print(f"  Constraint warning: {e}")


def load_accounts(driver, rows: List[Dict[str, Any]]) -> None:
    batches = split_batches(rows, BATCH_SIZE)
    with driver.session(database=NEO4J_DATABASE) as session:
        for b in batches:
            session.run(CYPHER_UPSERT_ACCOUNTS, rows=b)


def load_relationships(driver, edges: List[Dict[str, Any]]) -> None:
    batches = split_batches(edges, BATCH_SIZE)
    with driver.session(database=NEO4J_DATABASE) as session:
        for b in batches:
            session.run(CYPHER_UPSERT_RELATIONSHIPS, rows=b)


# =============================================================================
# Main
# =============================================================================
def main():
    print("=== NCRP MSSQL -> Neo4j ETL (Corrected Data Model) ===")
    print(f"MSSQL: {MSSQL_SERVER} / {MSSQL_DATABASE}")
    print(f"Neo4j: {NEO4J_URI} / database: {NEO4J_DATABASE}")

    mssql = get_mssql_conn()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        print("\n[1/5] Cleaning up existing NCRP data...")
        cleanup_ncrp_data(driver)

        print("[2/5] Applying constraints/indexes...")
        apply_constraints(driver)

        print("[3/5] Extracting MoneyTransferTo from MSSQL...")
        transfer_rows = extract_transfers(mssql)
        print(f"  Transfer rows: {len(transfer_rows)}")

        print("[4/5] Building and loading Account nodes...")
        all_nodes = build_all_nodes(transfer_rows)
        victim_count = sum(1 for n in all_nodes if n["account_type"] == "victim")
        child_count = len(all_nodes) - victim_count
        print(f"  Total nodes: {len(all_nodes)} "
              f"(Victims/Layer0: {victim_count}, Others: {child_count})")
        load_accounts(driver, all_nodes)

        print("[5/5] Building and loading relationships...")
        edges = build_relationships(transfer_rows)
        print(f"  Relationships: {len(edges)}")
        load_relationships(driver, edges)

        print(f"\nDone. {len(all_nodes)} nodes, {len(edges)} relationships "
              f"loaded into '{NEO4J_DATABASE}'.")

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
