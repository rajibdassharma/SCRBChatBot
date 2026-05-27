"""
Add the local test fixture (TestDistrict + Test PS + 3 test users) to
the CURRENT database — works on LOCAL and PRODUCTION alike.

Whereas `seed_test_user.py` is local-only (per CLAUDE.md convention),
this script is explicitly safe to run on the production server. It:

  - Is idempotent — re-running is a no-op (checks by username / name).
  - Touches only the new test rows; never modifies real PSes or users.
  - Hashes passwords via the same passlib bcrypt path the login uses, so
    the generated hashes verify correctly.

Adds:
  units             TestDistrict
  police_stations   Test PS  (under TestDistrict)
  users             test_ps_admin   role=admin        pwd=TestAdmin@2026
                    test_ps_user    role=unit_user    pwd=TestUser@2026
                    test_ps_super   role=super_admin  pwd=TestSuper@2026

All three users have must_change_password=False so the fixed passwords
work immediately.

Usage:
  Local:
    cd c:\\VSCProjects\\SCRBChatBot\\CyberFraudDataEntry\\backend
    python add_test_users.py

  Server (after scp / git pull):
    cd /opt/cyberfraud/backend
    venv/bin/python add_test_users.py

DB credentials come from backend/.env (CFDSR_DB_*).
"""

import asyncio

from sqlalchemy import select

from database import engine, Base, async_session
import models  # noqa: F401 — registers all ORM models on Base.metadata
from models.unit import Unit
from models.police_station import PoliceStation
from models.user import User
from auth.security import hash_password


TEST_DISTRICT = "TestDistrict"
TEST_DISTRICT_CODE = "testdistrict"
TEST_STATION = "Test PS"

TEST_USERS = [
    # (username,        plaintext_pwd,     full_name,          role)
    ("test_ps_admin",   "TestAdmin@2026",  "Test Admin",       "admin"),
    ("test_ps_user",    "TestUser@2026",   "Test User",        "unit_user"),
    ("test_ps_super",   "TestSuper@2026",  "Test Super Admin", "super_admin"),
]


async def main() -> None:
    # Ensure tables exist (no-op if they already do)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # ── 1. District (units table) ────────────────────────────────
        unit = (await session.execute(
            select(Unit).where(Unit.name == TEST_DISTRICT)
        )).scalar_one_or_none()
        if unit is None:
            unit = Unit(name=TEST_DISTRICT, code=TEST_DISTRICT_CODE)
            session.add(unit)
            await session.flush()
            print(f"  + unit '{TEST_DISTRICT}' created (id={unit.id})")
        else:
            print(f"  = unit '{TEST_DISTRICT}' already exists (id={unit.id})")

        # ── 2. Police Station (no UNIQUE constraint — check first) ──
        ps = (await session.execute(
            select(PoliceStation).where(
                PoliceStation.district_name == TEST_DISTRICT,
                PoliceStation.station_name == TEST_STATION,
            )
        )).scalar_one_or_none()
        if ps is None:
            ps = PoliceStation(
                district_name=TEST_DISTRICT,
                station_name=TEST_STATION,
            )
            session.add(ps)
            await session.flush()
            print(f"  + PS '{TEST_STATION}' created (id={ps.id})")
        else:
            print(f"  = PS '{TEST_STATION}' already exists (id={ps.id})")

        # ── 3. Test users ────────────────────────────────────────────
        created = 0
        skipped = 0
        for username, plaintext, full_name, role in TEST_USERS:
            existing = (await session.execute(
                select(User).where(User.username == username)
            )).scalar_one_or_none()
            if existing is not None:
                print(f"  = user '{username}' already exists (role={existing.role})")
                skipped += 1
                continue
            session.add(User(
                username=username,
                hashed_password=hash_password(plaintext),
                full_name=full_name,
                role=role,
                unit_id=unit.id,
                ps_id=ps.id,
                must_change_password=False,
            ))
            created += 1
            print(f"  + user '{username}' created (role={role})")

        await session.commit()

    print()
    print("=" * 60)
    print("  TEST CREDENTIALS (LOCAL + PRODUCTION)")
    print("=" * 60)
    print(f"  District : {TEST_DISTRICT}")
    print(f"  PS       : {TEST_STATION}")
    print()
    for username, plaintext, _, role in TEST_USERS:
        print(f"  {role:<12s} : {username:<16s} / {plaintext}")
    print("=" * 60)
    print(f"  Created : {created} user(s)")
    print(f"  Skipped : {skipped} (already existed)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
