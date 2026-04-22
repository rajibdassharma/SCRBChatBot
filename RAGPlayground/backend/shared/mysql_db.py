"""
MySQL connection helper for RAG Playground.
"""

import pymysql
import pymysql.cursors
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE


def ensure_database_exists() -> None:
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST, port=MYSQL_PORT,
            user=MYSQL_USER, password=MYSQL_PASSWORD,
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
        print(f"[MySQL] WARNING: Could not ensure database: {exc}")


def get_conn() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
    )


ensure_database_exists()
