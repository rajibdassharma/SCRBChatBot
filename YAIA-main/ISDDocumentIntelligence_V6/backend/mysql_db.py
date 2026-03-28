"""
MySQL connection helper for ISD Document Intelligence.

Provides:
  - ensure_database_exists()  — creates the database if absent
  - get_conn()                — returns a pymysql.Connection (autocommit=False)
  - _fetchone(cursor)         — returns dict or None from current cursor position
  - _fetchall(cursor)         — returns list[dict] from current cursor position

The module calls ensure_database_exists() on first import so that the
database is ready before any table-level init_db() functions run.

NOTE: pymysql uses ``%s`` placeholders (NOT ``?``).  All SQL queries
executed through connections returned by get_conn() must use ``%s``
for parameter substitution.
"""

import pymysql
import pymysql.cursors
from config import (
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
)


# ---------------------------------------------------------------------------
# Database bootstrap
# ---------------------------------------------------------------------------

def ensure_database_exists() -> None:
    """
    Connect to the MySQL server (without selecting a database) and create
    the target database if it does not already exist.

    Called once at module import time so all subsequent init_db() calls
    can assume the database is present.
    """
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            autocommit=True,
        )
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.close()
        print(f"[MySQL] Database '{MYSQL_DATABASE}' is ready on {MYSQL_HOST}:{MYSQL_PORT}")
    except Exception as exc:
        print(
            f"[MySQL] WARNING: Could not ensure database '{MYSQL_DATABASE}' exists: {exc}\n"
            f"  -> Check MYSQL_HOST / MYSQL_USER / MYSQL_PASSWORD settings in backend/.env\n"
            f"  -> Host: {MYSQL_HOST}  Port: {MYSQL_PORT}  User: {MYSQL_USER}"
        )


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

def get_conn() -> pymysql.connections.Connection:
    """
    Return a pymysql Connection with autocommit=False (explicit commit required).

    The connection uses DictCursor by default so that fetchone() returns a dict
    and fetchall() returns a list of dicts.
    """
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
    )


# ---------------------------------------------------------------------------
# Row conversion helpers
# ---------------------------------------------------------------------------

def _fetchone(cursor):
    """
    Consume the next row from *cursor* and return it as a dict (or None).

    Because get_conn() already uses DictCursor, this is a thin wrapper
    kept for API compatibility with callers that expect this helper.
    """
    return cursor.fetchone()


def _fetchall(cursor):
    """
    Consume all remaining rows from *cursor* and return as list[dict].

    Because get_conn() already uses DictCursor, this is a thin wrapper
    kept for API compatibility with callers that expect this helper.
    """
    return cursor.fetchall()


# ---------------------------------------------------------------------------
# Module-level bootstrap
# ---------------------------------------------------------------------------
ensure_database_exists()
