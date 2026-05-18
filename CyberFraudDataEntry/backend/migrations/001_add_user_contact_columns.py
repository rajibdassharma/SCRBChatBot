"""
Migration 001 — add contact + audit columns to the `users` table.

Adds five NULLABLE columns:
  - email        VARCHAR(200)  + UNIQUE INDEX
  - mobile       VARCHAR(20)
  - created_by   INT           (who created this user)
  - deactivated_at DATETIME    (when deactivated; NULL = active)
  - deactivated_by INT         (who deactivated)

Why NULLABLE in the DB but required at the API layer:
  - The 88 already-seeded production users have no email/mobile data.
  - Making the columns NOT NULL would require a placeholder backfill
    that's worse than just letting them be NULL until an admin edits
    them via the new User Management page.
  - The Pydantic schema for `POST /users` enforces both as required for
    NEWLY CREATED users — the only path that should produce them.
  - The UNIQUE INDEX on email allows multiple NULLs in MySQL.

Idempotent — safe to re-run. Uses INFORMATION_SCHEMA checks so it works
on MySQL 5.7, 8.0, and 8.0.29+ alike (no reliance on `IF NOT EXISTS`).

Usage:  python -m migrations.001_add_user_contact_columns
"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from database import engine
from config import settings


# (column_name, column_def) — column_def goes after `ADD COLUMN <name> `
_COLUMNS: list[tuple[str, str]] = [
    ("email", "VARCHAR(200) NULL"),
    ("mobile", "VARCHAR(20) NULL"),
    ("created_by", "INT NULL"),
    ("deactivated_at", "DATETIME NULL"),
    ("deactivated_by", "INT NULL"),
]

# (index_name, is_unique, column_list)
_INDEXES: list[tuple[str, bool, str]] = [
    ("ix_users_email_unique", True, "email"),
    ("ix_users_ps_id", False, "ps_id"),
    ("ix_users_created_by", False, "created_by"),
]


async def _column_exists(conn: AsyncConnection, table: str, column: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND COLUMN_NAME = :col"
        ),
        {"db": settings.DB_NAME, "tbl": table, "col": column},
    )
    return row.first() is not None


async def _index_exists(conn: AsyncConnection, table: str, index: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND INDEX_NAME = :idx"
        ),
        {"db": settings.DB_NAME, "tbl": table, "idx": index},
    )
    return row.first() is not None


async def run() -> None:
    print("Running migration 001 — add user contact + audit columns")
    async with engine.begin() as conn:
        # Columns
        for name, ddl in _COLUMNS:
            if await _column_exists(conn, "users", name):
                print(f"  = users.{name} already exists, skipping")
                continue
            stmt = f"ALTER TABLE users ADD COLUMN {name} {ddl}"
            print(f"  + {stmt}")
            await conn.execute(text(stmt))

        # Indexes
        for index_name, is_unique, column_list in _INDEXES:
            if await _index_exists(conn, "users", index_name):
                print(f"  = index {index_name} already exists, skipping")
                continue
            kind = "UNIQUE INDEX" if is_unique else "INDEX"
            stmt = f"CREATE {kind} {index_name} ON users ({column_list})"
            print(f"  + {stmt}")
            await conn.execute(text(stmt))

    print("Migration 001 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
