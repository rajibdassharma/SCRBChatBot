"""
Migration 005 — create the `chat_messages` audit table.

One row per chat question. Captures the user, the question, the SQL we
generated (or NULL if generation failed), the row count, any error
message, and the end-to-end latency.

Idempotent.

Usage:
  python -m migrations.005_add_chat_messages
"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from database import engine
from config import settings


async def _table_exists(conn: AsyncConnection, table: str) -> bool:
    row = await conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl"
        ),
        {"db": settings.DB_NAME, "tbl": table},
    )
    return row.first() is not None


async def run() -> None:
    print("Running migration 005 — add chat_messages table")
    async with engine.begin() as conn:
        if await _table_exists(conn, "chat_messages"):
            print("  = chat_messages already exists, skipping")
        else:
            print("  + CREATE TABLE chat_messages")
            await conn.execute(text("""
                CREATE TABLE chat_messages (
                    id              VARCHAR(36) NOT NULL,
                    user_id         INT NOT NULL,
                    unit_id         INT NULL,
                    ps_id           INT NULL,
                    question        TEXT NOT NULL,
                    generated_sql   TEXT NULL,
                    row_count       INT NULL,
                    error           VARCHAR(500) NULL,
                    latency_ms      INT NULL,
                    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    INDEX ix_chat_messages_user_id (user_id),
                    INDEX ix_chat_messages_created_at (created_at),
                    CONSTRAINT fk_chat_messages_user_id
                        FOREIGN KEY (user_id) REFERENCES users(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
    print("Migration 005 complete.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
