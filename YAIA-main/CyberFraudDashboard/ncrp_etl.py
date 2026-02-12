"""
ETL: Read Excel file(s) in a folder (all tabs) and load into 6 category-specific
SQL Server tables in DB: NCRP.

Tables:
  dbo.MoneyTransferTo, dbo.OtherTransactions, dbo.PutOnHold,
  dbo.OthersLessThan500, dbo.AEPS, dbo.ATMWithdrawal

Each Excel sheet maps to one table via SHEET_CATEGORY_MAP -> TABLE_CONFIG.

Prereqs:
  pip install pandas openpyxl pyodbc

Usage:
  1) Set TEST_SINGLE_FILE=True and set SINGLE_FILE_NAME to one xlsx filename for test
  2) (Optional) WIPE_TABLE_BEFORE_LOAD=True to delete all rows before test run
  3) Run: python ncrp_etl.py
"""

import os
import glob
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pyodbc

# -----------------------------
# CONFIG
# -----------------------------
FOLDER_PATH = r"C:\Users\Rajib Das Sharma\OneDrive\Desktop\CID Data\Cyber Fraud"
SQL_DATABASE = "NCRP"
SQL_SERVER = "localhost"

CONN_STR = (
    "Driver={ODBC Driver 18 for SQL Server};"
    f"Server={SQL_SERVER};"
    f"Database={SQL_DATABASE};"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

# --- TEST MODE (recommended) ---
TEST_SINGLE_FILE = False
SINGLE_FILE_NAME = r"21612250083721 BankAction_CompleteTrail09_01_2026 12_00_09.xlsx"
WIPE_TABLE_BEFORE_LOAD = True

ENABLE_DEDUP = False


# -----------------------------
# TABLE CONFIGURATION: one entry per category/sheet type
# -----------------------------
TABLE_CONFIG: Dict[str, dict] = {
    "MONEY_TRANSFER_TO": {
        "table": "dbo.MoneyTransferTo",
        "columns": [
            "SNo", "AcknowledgementNo", "AccountOrWalletId", "TransactionUTR",
            "BankFIs", "Layer", "AccountNo", "IFSCCode", "TransactionDate",
            "TransactionUTR2", "TransactionAmount", "DisputedAmount",
            "ReferenceNo", "Remarks", "ActionTakenByBank", "DateOfAction", "PISNodal",
        ],
    },
    "OTHER": {
        "table": "dbo.OtherTransactions",
        "columns": [
            "SNo", "AcknowledgementNo", "AccountOrWalletId", "TransactionUTR",
            "OtherDate", "TransactionAmount", "OtherAmount",
            "ReferenceNo", "Remarks", "ActionTakenByBank", "DateOfAction", "PISNodal",
        ],
    },
    "PUT_ON_HOLD": {
        "table": "dbo.PutOnHold",
        "columns": [
            "SNo", "AcknowledgementNo", "AccountOrWalletId", "TransactionUTR",
            "PutOnHoldDate", "PutOnHoldAmount", "ActionTakenByBank",
            "DateOfAction", "Layer", "PISNodal",
        ],
    },
    "OTHERS_LT_500": {
        "table": "dbo.OthersLessThan500",
        "columns": [
            "SNo", "AcknowledgementNo", "AccountOrWalletId", "TransactionUTR",
            "ReferenceNo", "Remarks", "ActionTakenByBank", "DateOfAction", "PISNodal",
        ],
    },
    "AEPS": {
        "table": "dbo.AEPS",
        "columns": [
            "SNo", "AcknowledgementNo", "AccountOrWalletId", "TransactionUTR",
            "WithdrawalDate", "WithdrawalAmount", "ReferenceNo", "Remarks",
            "ActionTakenByBank", "DateOfAction", "ParentTrans", "ParentAccountNo",
            "ParentIFSCCode", "ParentLayer", "PISNodal",
        ],
    },
    "ATM_WITHDRAWAL": {
        "table": "dbo.ATMWithdrawal",
        "columns": [
            "SNo", "AcknowledgementNo", "AccountOrWalletId", "TransactionUTR",
            "WithdrawalDateTime", "WithdrawalAmount", "DisputedAmount",
            "ATMID", "ATMLocation", "ReferenceNo", "Remarks",
            "ActionTakenByBank", "DateOfAction", "PISNodal",
        ],
    },
}

# Map Excel sheet names -> Category
SHEET_CATEGORY_MAP: Dict[str, str] = {
    "money transfer to": "MONEY_TRANSFER_TO",
    "other": "OTHER",
    "transaction put on hold": "PUT_ON_HOLD",
    "others less then 500": "OTHERS_LT_500",
    "others less than 500": "OTHERS_LT_500",
    "aeps": "AEPS",
    "withdrawal through atm": "ATM_WITHDRAWAL",
    "withdrawal through atms": "ATM_WITHDRAWAL",
    "atm withdrawal": "ATM_WITHDRAWAL",
}

# Column synonym map (Excel headers vary slightly across tabs)
COLUMN_MAP: Dict[str, str] = {
    "s no.": "SNo",
    "s no": "SNo",
    "sno": "SNo",

    "acknowledgement no.": "AcknowledgementNo",
    "acknowledgement no": "AcknowledgementNo",

    "account no./ (wallet /pg/pa) id": "AccountOrWalletId",
    "account no / (wallet /pg/pa) id": "AccountOrWalletId",
    "account no./(wallet/pg/pa) id": "AccountOrWalletId",
    "account no": "AccountNo",
    "account no.": "AccountNo",

    "transaction id / utr number": "TransactionUTR",
    "transaction id/ utr number": "TransactionUTR",
    "transaction id / utr no": "TransactionUTR",
    "transaction id / utr number2": "TransactionUTR2",
    "transaction id / utr number 2": "TransactionUTR2",

    "reference no": "ReferenceNo",
    "reference no.": "ReferenceNo",

    "remarks": "Remarks",
    "action taken by bank": "ActionTakenByBank",
    "date of action": "DateOfAction",
    "pisnodal": "PISNodal",

    "bank/fis": "BankFIs",
    "bank/fis ": "BankFIs",
    "layer": "Layer",
    "ifsc code": "IFSCCode",

    "transaction date": "TransactionDate",
    "transaction amount": "TransactionAmount",
    "disputed amount": "DisputedAmount",

    "date": "OtherDate",

    "put on hold date": "PutOnHoldDate",
    "put on hold amount": "PutOnHoldAmount",

    "withdrawal date": "WithdrawalDate",
    "withdrawal amount": "WithdrawalAmount",
    "ptrans": "ParentTrans",
    "paccountno": "ParentAccountNo",
    "pifsc_code": "ParentIFSCCode",
    "players": "ParentLayer",

    "withdrawal date & time": "WithdrawalDateTime",
    "atm id": "ATMID",
    "place/location of atm": "ATMLocation",
    "place / location of atm": "ATMLocation",
}

# Column type classification
ALL_DATE_COLS = {
    "DateOfAction", "TransactionDate", "OtherDate",
    "PutOnHoldDate", "WithdrawalDate", "WithdrawalDateTime",
}
ALL_DEC_COLS = {
    "TransactionAmount", "DisputedAmount", "OtherAmount",
    "PutOnHoldAmount", "WithdrawalAmount",
}
ALL_INT_COLS = {"SNo", "Layer", "ParentLayer"}


# -----------------------------
# HELPERS
# -----------------------------
def norm(s: str) -> str:
    """Normalize sheet/column names for robust matching."""
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def parse_datetime_series(series: pd.Series) -> pd.Series:
    """
    Parse dates robustly.
    - Keeps NaT for invalid
    - Handles Excel datetime + strings
    - Fixes non-standard ":AM"/":PM" suffix (e.g. "13:34:PM", "10:35:AM")
      These use 24-hour time with a redundant AM/PM tag, so we strip it.
    - Preserves standard " AM"/" PM" format (e.g. "10:35:00 AM")
    """
    s = series.astype("string")
    s = s.str.replace(r":([AP]M)\s*$", "", regex=True)
    return pd.to_datetime(s, errors="coerce", dayfirst=True, utc=False)


def parse_decimal_series(series: pd.Series) -> pd.Series:
    """Parse decimals robustly; strips commas and non-numeric noise."""
    s = series.astype("string").str.strip()
    s = s.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    s = s.str.replace(",", "", regex=False)
    s = s.str.replace(r"[^\d\.\-]", "", regex=True)
    return pd.to_numeric(s, errors="coerce")


def parse_int_series(series: pd.Series) -> pd.Series:
    """Parse ints robustly."""
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def get_identity_columns(conn: pyodbc.Connection, table_fullname: str) -> List[str]:
    """
    Detect identity columns in the target table so we never insert into them.
    Works for dbo.TableName or schema.table.
    """
    if "." in table_fullname:
        schema, table = table_fullname.split(".", 1)
    else:
        schema, table = "dbo", table_fullname

    sql = """
    SELECT c.name
    FROM sys.columns c
    INNER JOIN sys.tables t ON c.object_id = t.object_id
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = ? AND t.name = ? AND c.is_identity = 1
    """
    cur = conn.cursor()
    rows = cur.execute(sql, (schema, table)).fetchall()
    return [r[0] for r in rows]


def ensure_series(obj) -> pd.Series:
    """
    Some Excel reads can produce duplicate column names -> pandas returns a DataFrame when selecting.
    We force it to be a Series (pick the first column) so .str works safely.
    """
    if isinstance(obj, pd.DataFrame):
        return obj.iloc[:, 0]
    return obj


def dataframe_from_sheet(xls_path: str, sheet_name: str) -> Optional[Tuple[str, pd.DataFrame]]:
    """Read a sheet and transform into the table-specific schema. Returns (category, df) or None."""
    sheet_key = norm(sheet_name)
    category = SHEET_CATEGORY_MAP.get(sheet_key)
    if not category:
        return None

    cfg = TABLE_CONFIG[category]
    table_cols = cfg["columns"]

    df = pd.read_excel(xls_path, sheet_name=sheet_name, dtype=str)
    if df is None or df.empty:
        return None

    # Rename columns using COLUMN_MAP
    mapped_cols = {}
    for col in df.columns:
        key = norm(str(col))
        if key in COLUMN_MAP:
            mapped_cols[col] = COLUMN_MAP[key]
    df = df.rename(columns=mapped_cols)

    # Remove duplicate columns after rename (keep first occurrence)
    df = df.loc[:, ~df.columns.duplicated()]

    # Ensure all table-specific columns exist
    for c in table_cols:
        if c not in df.columns:
            df[c] = pd.NA

    # Special case: OTHER sheet uses TransactionAmount but should also land in OtherAmount
    if category == "OTHER":
        if df["OtherAmount"].isna().all() and df["TransactionAmount"].notna().any():
            df["OtherAmount"] = df["TransactionAmount"]

    # Coerce AcknowledgementNo
    df["AcknowledgementNo"] = pd.to_numeric(
        ensure_series(df["AcknowledgementNo"]), errors="coerce"
    ).astype("Int64")

    # Coerce types -- only for columns in this table
    for c in table_cols:
        if c == "AcknowledgementNo":
            continue  # already handled
        if c in ALL_DATE_COLS:
            df[c] = parse_datetime_series(ensure_series(df[c]))
        elif c in ALL_DEC_COLS:
            df[c] = parse_decimal_series(ensure_series(df[c]))
        elif c in ALL_INT_COLS:
            df[c] = parse_int_series(ensure_series(df[c]))
        else:
            ser = ensure_series(df[c])
            df[c] = ser.astype("string").str.strip()

    # Keep only this table's columns
    df = df[table_cols]

    # Drop rows without AcknowledgementNo
    df = df[df["AcknowledgementNo"].notna()]

    return (category, df)


def df_to_records(df: pd.DataFrame) -> List[Tuple]:
    """
    Convert dataframe to list of Python tuples with only Python-native types.
    This avoids pyodbc 'describe' issues.
    """
    records = []
    for row in df.itertuples(index=False, name=None):
        out = []
        for v in row:
            if pd.isna(v):
                out.append(None)
            elif isinstance(v, pd.Timestamp):
                out.append(v.to_pydatetime().replace(tzinfo=None))
            elif hasattr(v, "item"):  # numpy scalar -> python scalar
                out.append(v.item())
            else:
                out.append(v)
        records.append(tuple(out))
    return records


def insert_dataframe(cursor, table_name: str, insert_cols: List[str], df: pd.DataFrame) -> int:
    """Bulk insert dataframe into the specified SQL Server table."""
    if df.empty:
        return 0

    placeholders = ",".join(["?"] * len(insert_cols))
    col_list = ",".join([f"[{c}]" for c in insert_cols])
    sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})"

    records = df_to_records(df[insert_cols])
    cursor.fast_executemany = True
    cursor.executemany(sql, records)
    return len(records)


def wipe_table(cur, table_name: str):
    cur.execute(f"DELETE FROM {table_name};")


def count_rows(cur, table_name: str) -> int:
    return cur.execute(f"SELECT COUNT(*) FROM {table_name};").fetchval()


def main():
    # Resolve file list
    if TEST_SINGLE_FILE:
        xls_path = os.path.join(FOLDER_PATH, SINGLE_FILE_NAME)
        excel_files = [xls_path] if os.path.exists(xls_path) else []
        if not excel_files:
            print(f"Single file not found: {xls_path}")
            return
    else:
        excel_files = sorted(glob.glob(os.path.join(FOLDER_PATH, "*.xlsx")))
        if not excel_files:
            print(f"No .xlsx files found in: {FOLDER_PATH}")
            return

    print(f"Found {len(excel_files)} Excel file(s).")

    conn = pyodbc.connect(CONN_STR)
    try:
        cur = conn.cursor()

        # Pre-compute identity columns and insert-column lists per table
        table_insert_cols: Dict[str, List[str]] = {}
        for cat, cfg in TABLE_CONFIG.items():
            tname = cfg["table"]
            identity = get_identity_columns(conn, tname)
            identity_lower = {c.lower() for c in identity}
            table_insert_cols[cat] = [
                c for c in cfg["columns"] if c.lower() not in identity_lower
            ]

        print(f"Connected to server: {SQL_SERVER}, DB: {SQL_DATABASE}")
        for cat, cfg in TABLE_CONFIG.items():
            print(f"  {cfg['table']}: {len(table_insert_cols[cat])} insert columns")

        # Wipe all tables if requested
        if WIPE_TABLE_BEFORE_LOAD:
            print("\nWiping all tables ...")
            for cat, cfg in TABLE_CONFIG.items():
                tname = cfg["table"]
                wipe_table(cur, tname)
            conn.commit()
            print("Wipe complete.")

        total_inserted = 0
        per_table_counts: Dict[str, int] = {cat: 0 for cat in TABLE_CONFIG}

        for xls_path in excel_files:
            print(f"\nProcessing: {os.path.basename(xls_path)}")
            try:
                xls = pd.ExcelFile(xls_path)
                file_inserted = 0

                for sheet in xls.sheet_names:
                    result = dataframe_from_sheet(xls_path, sheet)
                    if result is None:
                        continue

                    category, df_sheet = result
                    if df_sheet.empty:
                        continue

                    cfg = TABLE_CONFIG[category]
                    tname = cfg["table"]
                    icols = table_insert_cols[category]

                    inserted = insert_dataframe(cur, tname, icols, df_sheet)
                    file_inserted += inserted
                    per_table_counts[category] += inserted
                    print(f"  {sheet} -> {tname}: {inserted} rows")

                conn.commit()
                total_inserted += file_inserted
                print(f"  Total from file: {file_inserted} rows")

            except Exception as e:
                conn.rollback()
                print(f"ERROR processing {xls_path}: {e}")

        # Summary
        print(f"\nDONE. Total rows inserted: {total_inserted}")
        print("Per-table summary:")
        for cat, cfg in TABLE_CONFIG.items():
            tname = cfg["table"]
            print(f"  {tname}: {count_rows(cur, tname)} rows")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
