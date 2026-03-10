"""
Migrate data from V4 (MSSQL) to V5 (MySQL).

Copies all table data from the MSSQL ISDIntelligence database into MySQL.
Also copies the ChromaDB folder (chroma_db_v4 -> chroma_db_v5).

Usage:
    cd ISDDocumentIntelligence_V5/dbscripts
    python migrate_mssql_to_mysql.py

Prerequisites:
    - MSSQL Server running with ISDIntelligence database (V4 data)
    - MySQL running with root access (password in V5 backend/.env)
    - pip install pyodbc pymysql python-dotenv
"""

import os, sys, shutil, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", ".env"))

import pyodbc
import pymysql

MSSQL_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;"
    "DATABASE=ISDIntelligence;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "ISDIntelligence")

BATCH_SIZE = 500

TABLES = [
    {
        "name": "users",
        "select": "SELECT id, username, password_hash, full_name, role, is_active, created_at FROM users",
        "insert": "INSERT IGNORE INTO users (id, username, password_hash, full_name, role, is_active, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
    },
    {
        "name": "cases",
        "select": "SELECT id, user_id, name, description, collection, created_at FROM cases",
        "insert": "INSERT IGNORE INTO cases (id, user_id, name, description, collection, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
    },
    {
        "name": "smac_reports",
        "select": "SELECT id, doc_id, doc_name, input_id, date_of_receipt, originator, source_name, grading, theatre, priority, subject, gist, threat_details, shared_with, classification, raw_fields, indexed_at FROM smac_reports",
        "insert": "INSERT IGNORE INTO smac_reports (id, doc_id, doc_name, input_id, date_of_receipt, originator, source_name, grading, theatre, priority, subject, gist, threat_details, shared_with, classification, raw_fields, indexed_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
    },
    {
        "name": "ir_reports",
        "select": "SELECT id, doc_id, doc_name, collection, serial_no, field_key, field_value FROM ir_reports",
        "insert": "INSERT IGNORE INTO ir_reports (id, doc_id, doc_name, collection, serial_no, field_key, field_value) VALUES (%s, %s, %s, %s, %s, %s, %s)",
    },
    {
        "name": "entities",
        "select": "SELECT id, name, type, doc_id, doc_name, context, case_id FROM entities",
        "insert": "INSERT IGNORE INTO entities (id, name, type, doc_id, doc_name, context, case_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
    },
    {
        "name": "relationships",
        "select": "SELECT id, source_entity_id, target_entity_id, relationship_type, doc_id, context, case_id FROM relationships",
        "insert": "INSERT IGNORE INTO relationships (id, source_entity_id, target_entity_id, relationship_type, doc_id, context, case_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
    },
    {
        "name": "activities",
        "select": "SELECT id, tms_id, doc_id, doc_name, activity_date, group_name, subject, description, temporal_status, priority, theatre, participants, activity_type, case_id FROM activities",
        "insert": "INSERT IGNORE INTO activities (id, tms_id, doc_id, doc_name, activity_date, group_name, subject, description, temporal_status, priority, theatre, participants, activity_type, case_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
    },
    {
        "name": "cross_references",
        "select": "SELECT id, source_tms_id, target_tms_id, context, doc_id, case_id FROM cross_references",
        "insert": "INSERT IGNORE INTO cross_references (id, source_tms_id, target_tms_id, context, doc_id, case_id) VALUES (%s, %s, %s, %s, %s, %s)",
    },
    {
        "name": "doc_locations",
        "select": "SELECT id, doc_id, doc_name, person_name, address_text, city, locality, lat, lng, address_type, case_id FROM doc_locations",
        "insert": "INSERT IGNORE INTO doc_locations (id, doc_id, doc_name, person_name, address_text, city, locality, lat, lng, address_type, case_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
    },
    {
        "name": "answer_ratings",
        "select": "SELECT id, user_id, username, collection, case_id, question, answer, rating, created_at FROM answer_ratings",
        "insert": "INSERT IGNORE INTO answer_ratings (id, user_id, username, collection, case_id, question, answer, rating, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
    },
]


def get_mssql_conn():
    return pyodbc.connect(MSSQL_CONN_STR)


def get_mysql_conn():
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.commit()
    conn.close()
    return pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD,
                           database=MYSQL_DATABASE, charset="utf8mb4")


def migrate_table(tbl, mssql_conn, mysql_conn):
    name = tbl["name"]
    print(); print("=" * 60)
    print(f"  Migrating: {name}")
    print(f"{'=' * 60}")
    try:
        cur = mssql_conn.cursor()
        cur.execute(tbl["select"])
        rows = cur.fetchall()
    except Exception as e:
        print(f"  SKIP (MSSQL error): {e}")
        return 0
    if not rows:
        print("  No data (0 rows)")
        return 0
    print(f"  Found {len(rows)} rows in MSSQL")
    data = [tuple(r) for r in rows]
    my_cur = mysql_conn.cursor()
    inserted = 0
    for i in range(0, len(data), BATCH_SIZE):
        batch = data[i:i + BATCH_SIZE]
        try:
            my_cur.executemany(tbl["insert"], batch)
            mysql_conn.commit()
            inserted += len(batch)
            print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} rows (total: {inserted})")
        except Exception as e:
            print(f"  ERROR batch {i // BATCH_SIZE + 1}: {e}")
            mysql_conn.rollback()
            for row in batch:
                try:
                    my_cur.execute(tbl["insert"], row)
                    mysql_conn.commit()
                    inserted += 1
                except Exception:
                    pass
    print(f"  Done: {inserted}/{len(rows)} rows")
    return inserted


def copy_chromadb():
    sd = os.path.dirname(os.path.abspath(__file__))
    src = os.path.abspath(os.path.join(sd, "..", "..", "ISDDocumentIntelligence_V4", "backend", "chroma_db_v4"))
    dst = os.path.abspath(os.path.join(sd, "..", "backend", "chroma_db_v5"))
    print(); print("=" * 60)
    print(f"  Copying ChromaDB")
    print(f"{'=' * 60}")
    print(f"  From: {src}")
    print(f"  To:   {dst}")
    if not os.path.exists(src):
        print(f"  ERROR: V4 ChromaDB not found")
        return False
    if os.path.exists(dst):
        print("  V5 ChromaDB already exists — skipping copy.")
        return True
    print("  Copying...")
    t0 = time.time()
    shutil.copytree(src, dst)
    mb = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fns in os.walk(dst) for f in fns) / (1024 * 1024)
    print(f"  Done: {mb:.1f} MB in {time.time() - t0:.1f}s")
    return True


def init_v5_tables(mysql_conn):
    print(); print("=" * 60)
    print(f"  Initializing V5 MySQL tables")
    print(f"{'=' * 60}")
    bd = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
    if bd not in sys.path:
        sys.path.insert(0, bd)
    old = os.getcwd()
    os.chdir(bd)
    try:
        from auth import init_users_table; init_users_table()
        from cases import init_cases_table; init_cases_table()
        from entity_graph import init_db as ig; ig()
        from activity_timeline import init_db as it; it()
        from location_extractor import init_db as il; il()
        from structured_tables import init_db as ist; ist()
        cur = mysql_conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS answer_ratings (
            id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL,
            username VARCHAR(100) NOT NULL, collection VARCHAR(50) NOT NULL DEFAULT 'SMAC',
            case_id INT NOT NULL DEFAULT 0, question TEXT, answer TEXT,
            rating INT NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        mysql_conn.commit()
        print("  All tables created")
    except Exception as e:
        print(f"  Warning: {e}")
    finally:
        os.chdir(old)


def main():
    print("=" * 60)
    print("  MSSQL -> MySQL Migration Script")
    print("  V4 (MSSQL) -> V5 (MySQL)")
    print("=" * 60)
    copy_chromadb()
    print(f"Connecting to MSSQL...")
    mssql = get_mssql_conn()
    print("  MSSQL connected")
    print(f"Connecting to MySQL ({MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE})...")
    mysql = get_mysql_conn()
    print("  MySQL connected")
    init_v5_tables(mysql)
    mysql = get_mysql_conn()
    total = 0
    for t in TABLES:
        total += migrate_table(t, mssql, mysql)
    # Reset AUTO_INCREMENT
    print(); print("=" * 60)
    print("  Resetting AUTO_INCREMENT counters")
    print(f"{'=' * 60}")
    mc = mysql.cursor()
    for tn in ["users", "cases", "entities", "relationships", "activities", "cross_references", "doc_locations", "answer_ratings"]:
        try:
            mc.execute(f"SELECT MAX(id) FROM `{tn}`")
            mx = mc.fetchone()[0]
            if mx:
                mc.execute(f"ALTER TABLE `{tn}` AUTO_INCREMENT = {mx + 1}")
                print(f"  {tn}: {mx + 1}")
        except Exception:
            pass
    mysql.commit()
    mssql.close()
    mysql.close()
    print(); print("=" * 60)
    print(f"  MIGRATION COMPLETE — {total} rows migrated")
    print(f"{'=' * 60}")
    print(); print("Next steps:")
    print("  1. Verify MySQL password in V5 backend/.env")
    print("  2. cd ../backend && uvicorn app:app --reload --port 8001")
    print("  3. Test queries in the frontend")


if __name__ == "__main__":
    main()
