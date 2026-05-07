"""
LOCAL TESTING ONLY — adds a throwaway district / PS / admin / unit_user
with known fixed passwords so you can poke at the UI without rotating
through the seeded CSV credentials.

Idempotent: re-running just prints the same credentials again. Run
AFTER `python seed.py` (so the production users + reference data
already exist), or stand-alone after `python reset_db.py` if you want
ONLY the test fixtures.

DO NOT run this on the server. The deploy script only invokes
`reset_db.py` + `seed.py`; this file is never reached automatically.

Usage:
    python seed_test_user.py
"""
import asyncio

from sqlalchemy import select

from database import engine, Base, async_session
import models  # noqa: F401  - registers all models on Base.metadata
from models.unit import Unit
from models.police_station import PoliceStation
from models.user import User
from auth.security import hash_password


# Fixed credentials — easy to remember, satisfy the 12+ char / mixed /
# digit / special policy. Change here if you want different ones; the
# server never sees this file.
TEST_DISTRICT = "TestDistrict"
TEST_STATION = "Test PS"
TEST_ADMIN_USERNAME = "test_admin"
TEST_ADMIN_PASSWORD = "TestAdmin@2026"
TEST_USER_USERNAME = "test_user"
TEST_USER_PASSWORD = "TestUser@2026"


async def main() -> None:
    # Make sure tables exist (no-op if they do)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # 1. District (Unit)
        unit = (await session.execute(
            select(Unit).where(Unit.name == TEST_DISTRICT)
        )).scalar_one_or_none()
        if not unit:
            unit = Unit(name=TEST_DISTRICT, code="testdistrict")
            session.add(unit)
            await session.flush()
            print(f"  + unit '{TEST_DISTRICT}' created (id={unit.id})")
        else:
            print(f"  = unit '{TEST_DISTRICT}' already exists (id={unit.id})")

        # 2. Police Station
        ps = (await session.execute(
            select(PoliceStation).where(
                PoliceStation.district_name == TEST_DISTRICT,
                PoliceStation.station_name == TEST_STATION,
            )
        )).scalar_one_or_none()
        if not ps:
            ps = PoliceStation(
                district_name=TEST_DISTRICT,
                station_name=TEST_STATION,
            )
            session.add(ps)
            await session.flush()
            print(f"  + PS '{TEST_STATION}' created (id={ps.id})")
        else:
            print(f"  = PS '{TEST_STATION}' already exists (id={ps.id})")

        # 3. Admin user
        admin = (await session.execute(
            select(User).where(User.username == TEST_ADMIN_USERNAME)
        )).scalar_one_or_none()
        if not admin:
            session.add(User(
                username=TEST_ADMIN_USERNAME,
                hashed_password=hash_password(TEST_ADMIN_PASSWORD),
                full_name="Test Admin",
                role="admin",
                unit_id=unit.id,
                ps_id=ps.id,
                must_change_password=False,
            ))
            print(f"  + user '{TEST_ADMIN_USERNAME}' created")
        else:
            print(f"  = user '{TEST_ADMIN_USERNAME}' already exists")

        # 4. Unit user
        normal = (await session.execute(
            select(User).where(User.username == TEST_USER_USERNAME)
        )).scalar_one_or_none()
        if not normal:
            session.add(User(
                username=TEST_USER_USERNAME,
                hashed_password=hash_password(TEST_USER_PASSWORD),
                full_name="Test User",
                role="unit_user",
                unit_id=unit.id,
                ps_id=ps.id,
                must_change_password=False,
            ))
            print(f"  + user '{TEST_USER_USERNAME}' created")
        else:
            print(f"  = user '{TEST_USER_USERNAME}' already exists")

        await session.commit()

    print()
    print("=" * 60)
    print("  TEST CREDENTIALS (local UI testing only)")
    print("=" * 60)
    print(f"  District: {TEST_DISTRICT}")
    print(f"  PS      : {TEST_STATION}")
    print()
    print(f"  admin   : {TEST_ADMIN_USERNAME} / {TEST_ADMIN_PASSWORD}")
    print(f"  user    : {TEST_USER_USERNAME} / {TEST_USER_PASSWORD}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
