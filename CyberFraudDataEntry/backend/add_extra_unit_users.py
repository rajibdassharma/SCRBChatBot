"""
Additive user-provisioning script — adds 2 extra unit_users per police
station (`<ps_code>_user2`, `<ps_code>_user3`) so each PS has 3 unit_users
in addition to the existing `<ps_code>_admin` + `<ps_code>_user`.

Safe to run on production:
- Additive only — never touches existing rows.
- Idempotent — re-running is a no-op for PSes that already have user2/user3.
- Each new user gets a UNIQUE random password (same generator as seed.py).
- must_change_password=True (DB default) — temp password is unusable for
  real work; the user is forced to set their own on first login.

Output:
- Credentials written to `seed_credentials_extra_<timestamp>.csv` next to
  this script. Distribute securely, then DELETE.

Usage:  python add_extra_unit_users.py
"""

import asyncio
import csv
import re
import secrets
import string
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from database import engine, async_session
import models  # noqa: F401 — registers all ORM models on Base.metadata
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


def _to_code(name: str) -> str:
    code = name.lower().strip()
    code = re.sub(r"[^a-z0-9]+", "_", code)
    return code.strip("_")


async def add_extra_users():
    async with async_session() as session:
        # Load PS + unit mapping
        ps_rows = (await session.execute(
            text(
                "SELECT ps.id, ps.district_name, ps.station_name, u.id "
                "FROM police_stations ps "
                "LEFT JOIN units u ON u.name = ps.district_name"
            )
        )).fetchall()

        existing_usernames = set(
            (await session.execute(text("SELECT username FROM users"))).scalars().all()
        )

        credentials_log: list[tuple[str, str, str, str]] = []
        added = 0
        skipped = 0

        for ps_id, district, station, unit_id in ps_rows:
            ps_code = _to_code(station)
            for suffix in ("user2", "user3"):
                username = f"{ps_code}_{suffix}"
                if username in existing_usernames:
                    skipped += 1
                    continue
                pwd = generate_strong_password()
                session.add(User(
                    username=username,
                    hashed_password=hash_password(pwd),
                    full_name=f"User ({suffix}) - {station}",
                    role="unit_user",
                    unit_id=unit_id,
                    ps_id=ps_id,
                ))
                credentials_log.append((username, pwd, "unit_user", station))
                existing_usernames.add(username)
                added += 1

        if added:
            await session.commit()
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            creds_path = Path(__file__).parent / f"seed_credentials_extra_{stamp}.csv"
            with creds_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["username", "password", "role", "station", "must_change_on_first_login"])
                for row in credentials_log:
                    w.writerow([*row, "yes"])
            print(f"\n{'='*70}")
            print(f"  Extra unit_users added: {added}")
            print(f"  Already present (skipped): {skipped}")
            print(f"  Credentials written to: {creds_path}")
            print(f"  DISTRIBUTE SECURELY, then DELETE this file.")
            print(f"  All new users MUST change password on first login.")
            print(f"{'='*70}\n")
        else:
            print(f"No new users added. All {skipped} target usernames already exist.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(add_extra_users())
