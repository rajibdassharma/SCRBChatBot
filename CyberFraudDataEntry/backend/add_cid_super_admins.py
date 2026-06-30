"""
Additive provisioning — creates one new police station and four
super_admin user accounts for it. Same shape as `add_extra_unit_users.py`.

What it does:
  1. Verifies the `Bangalore City` unit (district) exists.
  2. Creates a `CID` police_station under that district if it doesn't
     already exist.
  3. Creates four super_admin users in that PS with the exact usernames:
       DYSPCCITR, DIGCCTR, SPCCITR, DGPCCITR
     Each gets a UNIQUE 16-char random password and
     must_change_password=True so they're forced to set their own on
     first login.

Safe to run on production:
  - Additive only — never touches existing rows.
  - Idempotent — skips the PS if it exists, skips any user whose
    username is already present. Re-running is a no-op.
  - Same password generator + hash function as seed.py / the UI
    create-user route, so credentials are interchangeable.

Output:
  - Credentials written to `seed_credentials_cid_<timestamp>.csv`
    next to this script. Distribute securely (in person / sealed
    envelope), then DELETE.

Usage:
    # local
    cd backend && python add_cid_super_admins.py

    # production
    sudo -u cyberfraud bash -c \\
      "cd /opt/cyberfraud/backend && venv/bin/python add_cid_super_admins.py"
"""

import asyncio
import csv
import secrets
import string
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from database import engine, async_session
import models  # noqa: F401 — registers all ORM models on Base.metadata
from models.police_station import PoliceStation
from models.user import User
from auth.security import hash_password


# Mirror seed.py's password generator exactly so hashes / strength match.
_PWD_CHARS_LOWER = string.ascii_lowercase
_PWD_CHARS_UPPER = string.ascii_uppercase
_PWD_CHARS_DIGIT = string.digits
_PWD_CHARS_SYM = "!@#$%^&*-_=+"
_PWD_ALL = _PWD_CHARS_LOWER + _PWD_CHARS_UPPER + _PWD_CHARS_DIGIT + _PWD_CHARS_SYM


def generate_strong_password(length: int = 16) -> str:
    if length < 8:
        raise ValueError("length must be >= 8")
    chars = [
        secrets.choice(_PWD_CHARS_LOWER),
        secrets.choice(_PWD_CHARS_UPPER),
        secrets.choice(_PWD_CHARS_DIGIT),
        secrets.choice(_PWD_CHARS_SYM),
    ]
    chars += [secrets.choice(_PWD_ALL) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


TARGET_DISTRICT = "Bengaluru City"
TARGET_STATION = "CID"

# Senior-officer designations. Usernames are kept as-given (uppercase, no
# underscores) since these are designation accounts, not per-PS user{N}
# operators. full_name defaults to the same string — operators can update
# it from the UI after first login.
SUPER_ADMIN_USERNAMES = ("DYSPCCITR", "DIGCCTR", "SPCCITR", "DGPCCITR")


async def provision_cid():
    async with async_session() as session:
        # ── 1. Resolve Bangalore City unit_id ────────────────────────
        unit_row = (await session.execute(
            text("SELECT id FROM units WHERE name = :n"),
            {"n": TARGET_DISTRICT},
        )).first()
        if not unit_row:
            raise RuntimeError(
                f"District '{TARGET_DISTRICT}' is not seeded in units. "
                f"Run seed.py first or check spelling — this script "
                f"refuses to invent a district."
            )
        unit_id = int(unit_row[0])
        print(f"Resolved district '{TARGET_DISTRICT}' → unit_id={unit_id}")

        # ── 2. Create the CID police station (idempotent) ────────────
        ps_row = (await session.execute(
            text(
                "SELECT id FROM police_stations "
                "WHERE district_name = :d AND station_name = :s"
            ),
            {"d": TARGET_DISTRICT, "s": TARGET_STATION},
        )).first()
        if ps_row:
            ps_id = int(ps_row[0])
            ps_action = "already existed"
        else:
            new_ps = PoliceStation(
                district_name=TARGET_DISTRICT,
                station_name=TARGET_STATION,
                is_active=True,
            )
            session.add(new_ps)
            await session.flush()
            ps_id = int(new_ps.id)
            ps_action = "created"
        print(f"Police station '{TARGET_STATION}' {ps_action} → ps_id={ps_id}")

        # ── 3. Create the four super_admin users (idempotent) ────────
        existing_usernames = set(
            (await session.execute(text("SELECT username FROM users"))).scalars().all()
        )

        credentials_log: list[tuple[str, str, str]] = []
        added = 0
        skipped = 0
        for username in SUPER_ADMIN_USERNAMES:
            if username in existing_usernames:
                print(f"  = {username} already exists, skipping")
                skipped += 1
                continue
            pwd = generate_strong_password()
            session.add(User(
                username=username,
                hashed_password=hash_password(pwd),
                full_name=username,        # placeholder — officers can edit
                role="super_admin",
                unit_id=unit_id,
                ps_id=ps_id,
                is_active=True,
                # must_change_password defaults to True via DB server_default
            ))
            credentials_log.append((username, pwd, "super_admin"))
            existing_usernames.add(username)
            added += 1
            print(f"  + {username}  (super_admin)")

        if added or ps_action == "created":
            await session.commit()

        # ── 4. Write the credentials CSV ─────────────────────────────
        if credentials_log:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            creds_path = Path(__file__).parent / f"seed_credentials_cid_{stamp}.csv"
            with creds_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "username", "password", "role",
                    "district", "station", "must_change_on_first_login",
                ])
                for username, pwd, role in credentials_log:
                    w.writerow([username, pwd, role, TARGET_DISTRICT, TARGET_STATION, "yes"])

            print(f"\n{'=' * 70}")
            print(f"  PS '{TARGET_STATION}' under '{TARGET_DISTRICT}': {ps_action}")
            print(f"  super_admin users added : {added}")
            print(f"  already present (skipped): {skipped}")
            print(f"  Credentials written to  : {creds_path}")
            print(f"  DISTRIBUTE SECURELY, then DELETE this file.")
            print(f"  All new users MUST change password on first login.")
            print(f"{'=' * 70}\n")
        else:
            print(
                f"\nNo new users added. All {skipped} target usernames "
                f"({', '.join(SUPER_ADMIN_USERNAMES)}) already exist."
            )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(provision_cid())
