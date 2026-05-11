"""
Drop every application table — for clean re-seeds during the pre-production
phase. After running this, run `python seed.py` to rebuild units, police
stations, and users from `All District CEN_PS.xlsx` and emit a fresh
`seed_credentials_*.csv`.

DO NOT run after real data exists. This is a destructive reset, safe only
because the seed data is the only data in the database. Once production
traffic starts, switch to per-table migrations instead.
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config import settings

ALL_TABLES = [
    # Case family
    "accomplices", "accused_details", "arrests",
    "petitions", "lien_accounts", "unfreeze_details", "refunds",
    "cases",
    # Mule report family
    "money_transfers", "other_transactions", "transactions_on_hold",
    "others_less_than_500", "aeps_transactions", "atm_withdrawals",
    "mule_reports",
    # User identity + daily entries
    "revoked_tokens",
    "mule_entries",
    "dsr_entries",
    "users",
    # Reference data (rebuilt from the Excel by seed.py)
    "police_stations",
    "units",
]


async def main() -> None:
    eng = create_async_engine(settings.database_url)
    async with eng.begin() as c:
        await c.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for t in ALL_TABLES:
            await c.execute(text(f"DROP TABLE IF EXISTS {t}"))
            print(f"  dropped {t}")
        await c.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    await eng.dispose()
    print("\nDone. Now run: python seed.py")


if __name__ == "__main__":
    asyncio.run(main())
