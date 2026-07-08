"""
One-off password reset for a locked-out user.

Use this when a KSP operator can't log in and the super_admin at
that PS can't (or won't) run the UI Reset Password action —
typical case is a PS admin who never completed the forced
password change and now nobody remembers the temp.

What it does:
  1. Looks up the user by username.
  2. Refuses if the account is inactive (won't unlock accounts
     that were deactivated on purpose).
  3. Generates a fresh 16-char random password + bcrypt hash.
  4. Overwrites hashed_password and sets must_change_password=True
     so the user is forced to set their own on next login.
  5. Prints the new password + writes it to
     `password_reset_<username>_<timestamp>.csv` in the backend
     directory. Distribute securely, then DELETE the file.

Safe on production:
  - Additive change to ONE user row. No schema change.
  - Idempotent — re-running generates a new password each time.
  - Same hash function + password generator as seed.py, so
    credentials are interchangeable.

Usage on the server:
  sudo -u cyberfraud bash -c \\
    "cd /opt/cyberfraud/backend && venv/bin/python \\
     reset_password_by_username.py <username>"

Usage locally:
  cd backend && python reset_password_by_username.py <username>
"""
import asyncio
import csv
import secrets
import string
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from auth.security import hash_password
from database import async_session, engine
import models  # noqa: F401 — registers all models on Base.metadata
from models.user import User


# Mirror seed.py's password generator exactly so strength matches.
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


async def reset_password(username: str) -> None:
    async with async_session() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()

        if not user:
            print(f"ERROR: No user with username {username!r} exists.", file=sys.stderr)
            print("       Check spelling, or list active users first:", file=sys.stderr)
            print("       sudo mysql -uroot -p... cyber_fraud_dsr -e \\", file=sys.stderr)
            print("            \"SELECT username, role, is_active FROM users\"", file=sys.stderr)
            sys.exit(1)

        if not user.is_active:
            print(f"ERROR: User {username!r} is INACTIVE.", file=sys.stderr)
            print("       Refusing to unlock a deactivated account. If this is", file=sys.stderr)
            print("       intentional, reactivate via the UI or manual UPDATE first.", file=sys.stderr)
            sys.exit(2)

        new_pwd = generate_strong_password()
        user.hashed_password = hash_password(new_pwd)
        user.must_change_password = True
        await session.commit()

        # Write the credentials CSV next to the script.
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        creds_path = Path(__file__).parent / f"password_reset_{username}_{stamp}.csv"
        with creds_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["username", "temp_password", "role", "must_change_on_first_login"])
            w.writerow([username, new_pwd, user.role, "yes"])

        print("=" * 70)
        print(f"  ✓ Password reset for {username!r}")
        print(f"    Role                    : {user.role}")
        print(f"    Full name               : {user.full_name or '(unset)'}")
        print(f"    New temp password       : {new_pwd}")
        print(f"    Credentials CSV         : {creds_path}")
        print(f"    must_change_on_first_login = yes")
        print("=" * 70)
        print("  Distribute the temp password SECURELY (in person / sealed).")
        print("  Then delete the CSV:")
        print(f"    sudo rm {creds_path}")
        print("  The user will be forced to change the password on next login.")
        print("=" * 70)

    await engine.dispose()


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    asyncio.run(reset_password(sys.argv[1].strip()))


if __name__ == "__main__":
    main()
