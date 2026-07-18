"""
Seed a batch of realistic test records into `all_accounts` so the
Entry screen + Account Details Dashboard can be exercised end-to-end
on a real environment.

Every record is tagged with `account_no` starting `TEST-` so the
matching purge script (`purge_all_accounts_test_data.py`) can strip
them cleanly without touching anything the operators entered.

Records span the three account types (Victim, Mule, Non-Mule) across
a handful of real banks + fake but plausible holder/herder names.
Mule rows carry 1-3 herders each so the child table gets exercised too.

USAGE (on the server, as the cyberfraud user):

    cd /opt/cyberfraud/backend
    venv/bin/python seed_all_accounts_test_data.py --ps-code CENPS_BLR_C

Args:
    --ps-code   REQUIRED. The `police_stations.code` value to attach
                every seeded row to (also drives which user gets set
                as submitted_by — first active user in that PS).
    --count     Optional. How many records to seed (default 30).
                Split roughly 50 % Victim, 30 % Mule, 20 % Non-Mule.

Idempotent-ish — running twice produces two separate test batches
(different UUIDs, different serial numbers). Run the purge script
first if you want to reset.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models.all_account import ACCOUNT_TYPES, AllAccount
from models.all_account_mule_herder import AllAccountMuleHerder
from models.police_station import PoliceStation
from models.user import User


# ── Sample data — plausible but obviously test-flavoured. ──────

BANKS = [
    ("State Bank of India",       "SBIN"),
    ("HDFC Bank",                 "HDFC"),
    ("ICICI Bank",                "ICIC"),
    ("Axis Bank",                 "UTIB"),
    ("Kotak Mahindra Bank",       "KKBK"),
    ("Punjab National Bank",      "PUNB"),
    ("Canara Bank",               "CNRB"),
    ("Bank of Baroda",            "BARB"),
    ("Yes Bank",                  "YESB"),
    ("IndusInd Bank",             "INDB"),
]

BRANCHES = [
    "MG Road", "Koramangala", "Whitefield", "Jayanagar", "Indiranagar",
    "Malleswaram", "HSR Layout", "BTM Layout", "Basavanagudi", "Ulsoor",
]

HOLDER_NAMES = [
    "Test Victim Ramesh Kumar",       "Test Victim Priya Reddy",
    "Test Victim Anil Sharma",         "Test Victim Deepa Iyer",
    "Test Victim Suresh Rao",          "Test Victim Meera Nair",
    "Test Mule Rajesh Singh",          "Test Mule Kavita Patel",
    "Test Mule Vikram Malhotra",       "Test Mule Sneha Joshi",
    "Test Mule Arjun Menon",           "Test NonMule Suspect Verma",
    "Test NonMule Suspect Choudhury",  "Test NonMule Suspect Bose",
]

HERDER_NAMES = [
    "Test Herder Ravi",   "Test Herder Vinod",  "Test Herder Prakash",
    "Test Herder Suresh", "Test Herder Manoj",  "Test Herder Kishore",
]

CITIES_KYC = [
    "Bengaluru", "Mysuru", "Hubballi", "Belagavi", "Mangaluru",
    "Kalaburagi", "Vijayapura", "Ballari", "Tumakuru", "Shivamogga",
]

TAG_PREFIX = "TEST-"


def _fake_account_no(i: int) -> str:
    # 12-digit numeric with TEST- prefix so grep + LIKE queries find them.
    return f"{TAG_PREFIX}{random.randint(100000000000, 999999999999)}-{i:03d}"


def _fake_ifsc(bank_code: str) -> str:
    return f"{bank_code}0{random.randint(100000, 999999)}"


def _fake_mobile() -> str:
    return f"9{random.randint(100000000, 999999999)}"


async def _resolve_ps_and_user(
    db: AsyncSession, ps_code: str,
) -> tuple[PoliceStation, User]:
    ps = (await db.execute(
        select(PoliceStation).where(PoliceStation.code == ps_code)
    )).scalar_one_or_none()
    if not ps:
        raise SystemExit(
            f"[!] No PoliceStation with code={ps_code!r}. "
            f"Check `SELECT code, station_name FROM police_stations` on the DB."
        )
    user = (await db.execute(
        select(User)
        .where(User.ps_id == ps.id, User.is_active == True)   # noqa: E712
        .order_by(User.id)
    )).scalars().first()
    if not user:
        raise SystemExit(
            f"[!] No active user attached to PS code={ps_code!r}. "
            f"Provision a user via seed.py or the User Management UI first."
        )
    return ps, user


async def _next_serial(db: AsyncSession, unit_id: int, ps_id: int) -> int:
    current_max = (await db.execute(
        select(func.coalesce(func.max(AllAccount.serial_no), 0))
        .where(AllAccount.unit_id == unit_id, AllAccount.ps_id == ps_id)
    )).scalar_one()
    return int(current_max) + 1


def _pick_type(i: int, total: int) -> str:
    """Roughly 50 % Victim, 30 % Mule, 20 % Non-Mule."""
    ratio = i / max(total, 1)
    if ratio < 0.50: return "Victim"
    if ratio < 0.80: return "Mule"
    return "Non-Mule"


async def seed(ps_code: str, count: int) -> None:
    random.seed(42)   # deterministic-ish so re-runs of the same batch look consistent
    async with async_session() as db:
        ps, user = await _resolve_ps_and_user(db, ps_code)
        print(f"Seeding into PS: {ps.station_name} (id={ps.id}, unit_id={ps.unit_id})")
        print(f"Recording as submitted_by user: {user.username} (id={user.id})")

        created_by_type = {"Victim": 0, "Mule": 0, "Non-Mule": 0}

        for i in range(count):
            acc_type = _pick_type(i, count)
            assert acc_type in ACCOUNT_TYPES

            bank_name, bank_code = random.choice(BANKS)
            branch = random.choice(BRANCHES)
            holder = random.choice(HOLDER_NAMES)
            city   = random.choice(CITIES_KYC)

            serial = await _next_serial(db, ps.unit_id, ps.id)
            row = AllAccount(
                id=str(uuid.uuid4()),
                unit_id=ps.unit_id,
                ps_id=ps.id,
                serial_no=serial,
                fir_no=f"{TAG_PREFIX}FIR-{i:03d}/2026",
                ncrp_ack_no=f"{TAG_PREFIX}NCRP-{random.randint(10**11, 10**12 - 1)}",
                account_no=_fake_account_no(i),
                bank_name=bank_name,
                branch_name=branch,
                ifsc_code=_fake_ifsc(bank_code),
                account_holder_name=holder,
                kyc_address=f"#{random.randint(1, 400)}, {branch}, {city} — KA-{random.randint(560000, 580000)}",
                kyc_mobile=_fake_mobile(),
                id_photo_path=None,
                account_type=acc_type,
                submitted_by=user.id,
                created_at=datetime.now(),
            )
            db.add(row)
            created_by_type[acc_type] += 1

            if acc_type == "Mule":
                for _ in range(random.randint(1, 3)):
                    db.add(AllAccountMuleHerder(
                        id=str(uuid.uuid4()),
                        account_id=row.id,
                        name=random.choice(HERDER_NAMES),
                        address=f"{random.choice(BRANCHES)}, {random.choice(CITIES_KYC)}",
                        mobile_no=_fake_mobile(),
                    ))

        await db.commit()

    print()
    print(f"=== Seeded {count} test records into `all_accounts` ===")
    for t, n in created_by_type.items():
        print(f"    {t:8s}: {n}")
    print()
    print(f"All rows carry `account_no` starting with '{TAG_PREFIX}'.")
    print(f"Purge them anytime with:")
    print(f"    venv/bin/python purge_all_accounts_test_data.py")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--ps-code", required=True, help="police_stations.code value to attach records to")
    parser.add_argument("--count", type=int, default=30, help="How many records to seed (default 30)")
    args = parser.parse_args()
    if args.count < 1 or args.count > 500:
        raise SystemExit("--count must be between 1 and 500")
    asyncio.run(seed(args.ps_code, args.count))


if __name__ == "__main__":
    main()
