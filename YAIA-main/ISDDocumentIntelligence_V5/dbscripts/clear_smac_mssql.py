"""
clear_smac_mssql.py — Delete all SMAC rows from smac_reports for a clean re-index.

Reads connection settings from ../backend/.env so server/database always match.

Run from the dbscripts folder:
    python clear_smac_mssql.py
"""
import os
import pyodbc
from dotenv import load_dotenv

# Load backend/.env — one level up from dbscripts/
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", ".env")
load_dotenv(_env_path)

server   = os.getenv("MSSQL_SERVER",   "localhost")
database = os.getenv("MSSQL_DATABASE", "ISDIntelligence")
driver   = os.getenv("MSSQL_DRIVER",   "ODBC Driver 17 for SQL Server")

conn_str = (
    f"DRIVER={{{driver}}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

print(f"Connecting to {server} / {database} ...")
conn = pyodbc.connect(conn_str)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM smac_reports")
count = cur.fetchone()[0]
print(f"Found {count} rows in smac_reports — deleting...")
cur.execute("DELETE FROM smac_reports")

conn.commit()
print("smac_reports cleared.")
conn.close()
