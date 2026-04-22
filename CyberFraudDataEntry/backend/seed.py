"""
Seed script: creates the MySQL database, tables, districts (units),
police stations, and users (2 per PS: admin + user).

Each user is seeded with a UNIQUE random password (CWE-521 hardening).
Credentials are written to `seed_credentials.csv` for the admin to
distribute securely. All seeded users have must_change_password=True
so they're forced to pick a new password at first login.

Usage:  python seed.py
"""

import asyncio
import csv
import re
import secrets
import string
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config import settings
from database import engine, Base, async_session
from pathlib import Path

from models import (
    Unit, User, Case, Arrest, Accomplice, AccusedDetail,
    Petition, LienAccount, UnfreezeDetail, Refund,
    MuleReport, MoneyTransfer, OtherTransaction, TransactionOnHold,
    OtherLessThan500, AepsTransaction, AtmWithdrawal,
    PoliceStation,
)
from auth.security import hash_password


# Password generation — 16 chars, mixed, satisfies validate_password_strength
_PWD_CHARS_LOWER = string.ascii_lowercase
_PWD_CHARS_UPPER = string.ascii_uppercase
_PWD_CHARS_DIGIT = string.digits
_PWD_CHARS_SYM = "!@#$%^&*-_=+"
_PWD_ALL = _PWD_CHARS_LOWER + _PWD_CHARS_UPPER + _PWD_CHARS_DIGIT + _PWD_CHARS_SYM


def generate_strong_password(length: int = 16) -> str:
    """Generate a cryptographically random password with at least one of
    each required character class."""
    if length < 8:
        raise ValueError("length must be >= 8")
    # Start with one of each required class, then fill the rest
    chars = [
        secrets.choice(_PWD_CHARS_LOWER),
        secrets.choice(_PWD_CHARS_UPPER),
        secrets.choice(_PWD_CHARS_DIGIT),
        secrets.choice(_PWD_CHARS_SYM),
    ]
    chars += [secrets.choice(_PWD_ALL) for _ in range(length - len(chars))]
    # Shuffle without bias
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _to_code(name: str) -> str:
    code = name.lower().strip()
    code = re.sub(r"[^a-z0-9]+", "_", code)
    return code.strip("_")


def _load_excel() -> list[tuple[str, str]]:
    """Load (district, station) pairs from All District CEN_PS.xlsx."""
    try:
        import openpyxl
    except ImportError:
        return []
    xlsx_path = Path(__file__).parent.parent / "All District CEN_PS.xlsx"
    if not xlsx_path.exists():
        # Fallback to old file
        xlsx_path = Path(__file__).parent.parent / "ALLDistrictPS.xlsx"
        if not xlsx_path.exists():
            return []
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        d = str(row[0]).strip() if row[0] else ""
        s = str(row[1]).strip() if row[1] else ""
        if d and s:
            rows.append((d, s))
    wb.close()
    return rows


async def create_database():
    """Create the database if it doesn't exist."""
    from urllib.parse import quote_plus
    pwd = quote_plus(settings.DB_PASSWORD)
    root_url = f"mysql+asyncmy://{settings.DB_USER}:{pwd}@{settings.DB_HOST}:{settings.DB_PORT}/"
    tmp_engine = create_async_engine(root_url, echo=False)
    async with tmp_engine.connect() as conn:
        await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{settings.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        await conn.commit()
    await tmp_engine.dispose()
    print(f"Database '{settings.DB_NAME}' ready.")


async def seed():
    await create_database()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created.")

    excel_rows = _load_excel()
    district_names = sorted(set(d for d, _ in excel_rows))

    async with async_session() as session:
        # ── 1. Seed districts as units ──
        existing_units = set(
            (await session.execute(text("SELECT code FROM units"))).scalars().all()
        )
        units_added = 0
        for name in district_names:
            code = _to_code(name)
            if code not in existing_units:
                session.add(Unit(name=name, code=code))
                units_added += 1
        await session.commit()
        print(f"Units (districts): {units_added} added, {len(existing_units)} already existed. Total: {len(district_names)}.")

        # Build unit name → id map
        all_units = (await session.execute(text("SELECT id, name FROM units"))).fetchall()
        unit_map = {name: uid for uid, name in all_units}

        # ── 2. Seed police stations ──
        existing_ps = set(
            (r[0], r[1]) for r in
            (await session.execute(text("SELECT district_name, station_name FROM police_stations"))).fetchall()
        )
        ps_added = 0
        for district, station in excel_rows:
            if (district, station) not in existing_ps:
                session.add(PoliceStation(district_name=district, station_name=station))
                ps_added += 1
        await session.commit()
        print(f"Police stations: {ps_added} added, {len(existing_ps)} already existed. Total: {len(excel_rows)}.")

        # Build PS name → id map
        all_ps = (await session.execute(
            text("SELECT id, district_name, station_name FROM police_stations")
        )).fetchall()
        ps_map = {(d, s): pid for pid, d, s in all_ps}

        # ── 3. Seed users per police station (2 per PS: admin + user) ──
        # Each user gets a UNIQUE random password. All seeded users are
        # forced to change password on first login (must_change_password=True
        # is the DB default).
        existing_usernames = set(
            (await session.execute(text("SELECT username FROM users"))).scalars().all()
        )

        credentials_log: list[tuple[str, str, str, str]] = []  # (username, password, role, station)
        users_added = 0
        print("Generating unique passwords and hashing (this may take a minute)...")

        for district, station in excel_rows:
            ps_code = _to_code(station)
            unit_id = unit_map.get(district)
            ps_id = ps_map.get((district, station))

            # Admin for this PS
            admin_username = f"{ps_code}_admin"
            if admin_username not in existing_usernames:
                admin_pwd = generate_strong_password()
                session.add(User(
                    username=admin_username,
                    hashed_password=hash_password(admin_pwd),
                    full_name=f"Admin - {station}",
                    role="admin",
                    unit_id=unit_id,
                    ps_id=ps_id,
                ))
                credentials_log.append((admin_username, admin_pwd, "admin", station))
                users_added += 1
                existing_usernames.add(admin_username)

            # User for this PS
            user_username = f"{ps_code}_user"
            if user_username not in existing_usernames:
                user_pwd = generate_strong_password()
                session.add(User(
                    username=user_username,
                    hashed_password=hash_password(user_pwd),
                    full_name=f"User - {station}",
                    role="unit_user",
                    unit_id=unit_id,
                    ps_id=ps_id,
                ))
                credentials_log.append((user_username, user_pwd, "unit_user", station))
                users_added += 1
                existing_usernames.add(user_username)

        if users_added:
            await session.commit()
            # Write credentials to a timestamped CSV so they can be distributed
            # and then the file deleted. gitignored — never commit.
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            creds_path = Path(__file__).parent / f"seed_credentials_{stamp}.csv"
            with creds_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["username", "password", "role", "station", "must_change_on_first_login"])
                for row in credentials_log:
                    w.writerow([*row, "yes"])
            print(f"\n{'='*70}")
            print(f"  PS users: {users_added} created with unique random passwords.")
            print(f"  Credentials written to: {creds_path}")
            print(f"  DISTRIBUTE SECURELY, then DELETE this file.")
            print(f"  All seeded users MUST change password on first login.")
            print(f"{'='*70}\n")
        else:
            print("PS users already exist.")

    await engine.dispose()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
