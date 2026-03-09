"""
MSSQL connection helper for ISD Document Intelligence.

Provides:
  - ensure_database_exists()  — creates the ISDIntelligenceV4 DB if absent
  - get_conn()                — returns a pyodbc.Connection (autocommit=False)
  - _fetchone(cursor)         — returns dict or None from current cursor position
  - _fetchall(cursor)         — returns list[dict] from current cursor position

The module calls ensure_database_exists() on first import so that the
database is ready before any table-level init_db() functions run.
"""

import pyodbc
from config import (
    MSSQL_SERVER,
    MSSQL_DATABASE,
    MSSQL_DRIVER,
    MSSQL_AUTH,
    MSSQL_USER,
    MSSQL_PASSWORD,
    MSSQL_CONNECTION_STRING,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _master_conn_string() -> str:
    """Connection string pointing to 'master' (for database creation)."""
    if MSSQL_AUTH.lower() == "windows":
        return (
            f"DRIVER={{{MSSQL_DRIVER}}};"
            f"SERVER={MSSQL_SERVER};"
            f"DATABASE=master;"
            f"Trusted_Connection=yes;"
            f"TrustServerCertificate=yes;"
        )
    return (
        f"DRIVER={{{MSSQL_DRIVER}}};"
        f"SERVER={MSSQL_SERVER};"
        f"DATABASE=master;"
        f"UID={MSSQL_USER};"
        f"PWD={MSSQL_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )


# ---------------------------------------------------------------------------
# Database bootstrap
# ---------------------------------------------------------------------------

def ensure_database_exists() -> None:
    """
    Connect to 'master' and create ISDIntelligenceV4 if it does not exist.
    Called once at module import time so all subsequent init_db() calls
    can assume the database is present.
    """
    try:
        # autocommit=True required for CREATE DATABASE outside a transaction
        conn = pyodbc.connect(_master_conn_string(), autocommit=True)
        conn.execute(
            f"IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = N'{MSSQL_DATABASE}') "
            f"CREATE DATABASE [{MSSQL_DATABASE}]"
        )
        conn.close()
        print(f"[MSSQL] Database '{MSSQL_DATABASE}' is ready on {MSSQL_SERVER}")
    except Exception as exc:
        print(
            f"[MSSQL] WARNING: Could not ensure database '{MSSQL_DATABASE}' exists: {exc}\n"
            f"  → Check MSSQL_SERVER / MSSQL_AUTH settings in backend/.env\n"
            f"  → Server: {MSSQL_SERVER}  Driver: {MSSQL_DRIVER}  Auth: {MSSQL_AUTH}"
        )


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

def get_conn() -> pyodbc.Connection:
    """Return a pyodbc Connection with autocommit=False (explicit commit required)."""
    conn = pyodbc.connect(MSSQL_CONNECTION_STRING)
    conn.autocommit = False
    return conn


# ---------------------------------------------------------------------------
# Row conversion helpers
# ---------------------------------------------------------------------------

def _fetchone(cursor: pyodbc.Cursor):
    """Consume the next row from *cursor* and return it as a dict (or None)."""
    row = cursor.fetchone()
    if row is None or cursor.description is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def _fetchall(cursor: pyodbc.Cursor):
    """Consume all remaining rows from *cursor* and return as list[dict]."""
    if cursor.description is None:
        return []
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Module-level bootstrap
# ---------------------------------------------------------------------------
ensure_database_exists()
