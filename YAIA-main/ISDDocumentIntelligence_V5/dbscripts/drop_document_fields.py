"""
drop_document_fields.py — One-time migration script.

Drops the old 'document_fields' table from MSSQL.
IR data is now stored in 'ir_reports' (created automatically when backend starts).

Run ONCE from the dbscripts folder:
    python drop_document_fields.py
"""
import os
import pyodbc
from dotenv import load_dotenv

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

cur.execute("""
    IF EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'document_fields'
    )
    BEGIN
        SELECT COUNT(*) FROM document_fields
    END
    ELSE
    BEGIN
        SELECT -1
    END
""")
count = cur.fetchone()[0]

if count == -1:
    print("document_fields table does not exist — nothing to do.")
else:
    print(f"Found document_fields with {count} rows — dropping table...")
    cur.execute("DROP TABLE document_fields")
    conn.commit()
    print("document_fields dropped successfully.")
    print("IR data will now be stored in ir_reports (created on next backend start).")

conn.close()
