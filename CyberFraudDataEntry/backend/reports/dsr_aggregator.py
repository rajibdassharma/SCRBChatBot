"""DSR aggregator — computes per-PS daily summary numbers live from the
operational tables (cases, arrests, petitions, lien_accounts, refunds,
mule_reports), filtered by `created_at` over a date range.

Used by `/api/v1/reports/dsr.pdf`. Returns plain dicts so the renderer
in `dsr_pdf.py` is agnostic to query mechanics.

PS scoping:
  - Cases / arrests / petitions / lien / refunds: scoped via the
    submitting user's ps_id (cases.submitted_by → users.ps_id). The
    cases table itself only carries unit_id (district), not ps_id.
  - Mule reports: same path (mule_reports.submitted_by → users.ps_id).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.case import Case
from models.arrest import Arrest
from models.petition import Petition
from models.lien_account import LienAccount
from models.refund import Refund
from models.mule_report import MuleReport
from models.user import User
from models.police_station import PoliceStation


# ── Result container ─────────────────────────────────────────────────


@dataclass
class DsrAggregateRow:
    """Numbers for one PS over the date range. When the report is for a
    single PS this is the only row; for "all PSes" mode the renderer
    builds one of these per active PS plus a totals row."""
    ps_id: Optional[int]
    ps_label: str  # "PS Name (District)" — or "TOTAL — All Police Stations"

    cases_total: int = 0
    cases_by_type: dict[str, int] = field(default_factory=dict)
    cases_by_crime: dict[str, int] = field(default_factory=dict)

    arrests_total: int = 0

    petitions_total: int = 0
    petitions_amount: float = 0.0

    lien_count: int = 0
    lien_amount: float = 0.0
    lien_by_bank: dict[str, tuple[int, float]] = field(default_factory=dict)  # bank -> (count, total)

    refunds_total: int = 0
    refunds_done: int = 0
    refunds_amount: float = 0.0

    mule_reports_total: int = 0


# ── Public API ───────────────────────────────────────────────────────


async def aggregate_dsr(
    db: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    ps_id: Optional[int] = None,
    district: Optional[str] = None,
) -> list[DsrAggregateRow]:
    """Compute the DSR aggregates over [from, to] for one of three scopes:

      - Single PS  : `ps_id=<id>` — returns 1 row
      - One district: `district=<name>` — returns N+1 rows (one per PS
                      in that district, then a TOTAL row scoped to the
                      district)
      - All PSes   : neither `ps_id` nor `district` — returns N+1 rows
                      (one per active PS that had activity, then a
                      grand TOTAL row)

    `ps_id` wins if both are passed (route enforces sensible inputs).
    """
    # Date window: inclusive of both ends → use [from 00:00, to+1 day 00:00)
    start_dt = datetime.combine(date_from, datetime.min.time())
    end_dt = datetime.combine(date_to + timedelta(days=1), datetime.min.time())

    if ps_id is not None:
        ps_label = await _ps_label(db, ps_id)
        row = await _aggregate_one(db, ps_id=ps_id, start=start_dt, end=end_dt, label=ps_label)
        return [row]

    # Multi-PS mode: collect the set of PSes to aggregate over. If
    # `district` is given, restrict to that district; otherwise all
    # active PSes.
    ps_q = (
        select(PoliceStation.id, PoliceStation.station_name, PoliceStation.district_name)
        .where(PoliceStation.is_active == True)  # noqa: E712
        .order_by(PoliceStation.district_name, PoliceStation.station_name)
    )
    if district:
        ps_q = ps_q.where(PoliceStation.district_name == district)
    ps_rows = (await db.execute(ps_q)).all()

    out: list[DsrAggregateRow] = []
    for pid, sname, dname in ps_rows:
        label = f"{sname} ({dname})"
        row = await _aggregate_one(db, ps_id=pid, start=start_dt, end=end_dt, label=label)
        # Skip PSes with zero activity to keep the report compact
        if (row.cases_total + row.arrests_total + row.petitions_total
                + row.lien_count + row.refunds_total + row.mule_reports_total) == 0:
            continue
        out.append(row)

    # Append totals row — label reflects the scope
    totals_label = (
        f"TOTAL — All Police Stations in {district}"
        if district
        else "TOTAL — All Police Stations"
    )
    totals = DsrAggregateRow(ps_id=None, ps_label=totals_label)
    for r in out:
        totals.cases_total += r.cases_total
        for k, v in r.cases_by_type.items():
            totals.cases_by_type[k] = totals.cases_by_type.get(k, 0) + v
        for k, v in r.cases_by_crime.items():
            totals.cases_by_crime[k] = totals.cases_by_crime.get(k, 0) + v
        totals.arrests_total += r.arrests_total
        totals.petitions_total += r.petitions_total
        totals.petitions_amount += r.petitions_amount
        totals.lien_count += r.lien_count
        totals.lien_amount += r.lien_amount
        for bank, (c, amt) in r.lien_by_bank.items():
            cur_c, cur_amt = totals.lien_by_bank.get(bank, (0, 0.0))
            totals.lien_by_bank[bank] = (cur_c + c, cur_amt + amt)
        totals.refunds_total += r.refunds_total
        totals.refunds_done += r.refunds_done
        totals.refunds_amount += r.refunds_amount
        totals.mule_reports_total += r.mule_reports_total
    out.append(totals)
    return out


# ── Internals ────────────────────────────────────────────────────────


async def _ps_label(db: AsyncSession, ps_id: int) -> str:
    row = (await db.execute(
        select(PoliceStation.station_name, PoliceStation.district_name)
        .where(PoliceStation.id == ps_id)
    )).first()
    if not row:
        return f"Police Station #{ps_id}"
    return f"{row[0]} ({row[1]})"


def _f(v) -> float:
    """Decimal/None-safe float conversion."""
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


async def _aggregate_one(
    db: AsyncSession,
    *,
    ps_id: int,
    start: datetime,
    end: datetime,
    label: str,
) -> DsrAggregateRow:
    """Run all 6 aggregation queries for one PS in the given window."""
    row = DsrAggregateRow(ps_id=ps_id, ps_label=label)
    in_window_case = and_(Case.created_at >= start, Case.created_at < end)

    # ── 1. Cases ──
    case_q = (
        select(Case.case_type, Case.crime_type, func.count().label("cnt"))
        .join(User, Case.submitted_by == User.id)
        .where(User.ps_id == ps_id, in_window_case)
        .group_by(Case.case_type, Case.crime_type)
    )
    for case_type, crime_type, cnt in (await db.execute(case_q)).all():
        row.cases_total += cnt
        if case_type:
            row.cases_by_type[case_type] = row.cases_by_type.get(case_type, 0) + cnt
        if crime_type:
            row.cases_by_crime[crime_type] = row.cases_by_crime.get(crime_type, 0) + cnt

    # ── 2. Arrests ──  (linked via case → user)
    arrest_q = (
        select(func.count())
        .select_from(Arrest)
        .join(Case, Arrest.case_id == Case.id)
        .join(User, Case.submitted_by == User.id)
        .where(User.ps_id == ps_id, Arrest.created_at >= start, Arrest.created_at < end)
    )
    row.arrests_total = (await db.execute(arrest_q)).scalar() or 0

    # ── 3. Petitions ──
    pet_q = (
        select(func.count(), func.coalesce(func.sum(Petition.amount), 0))
        .select_from(Petition)
        .join(Case, Petition.case_id == Case.id)
        .join(User, Case.submitted_by == User.id)
        .where(User.ps_id == ps_id, Petition.created_at >= start, Petition.created_at < end)
    )
    cnt, amt = (await db.execute(pet_q)).first() or (0, 0)
    row.petitions_total = cnt or 0
    row.petitions_amount = _f(amt)

    # ── 4. Lien accounts (with per-bank breakdown) ──
    lien_q = (
        select(
            LienAccount.bank_name,
            func.count(),
            func.coalesce(func.sum(LienAccount.amount_lien_marked), 0),
        )
        .select_from(LienAccount)
        .join(Case, LienAccount.case_id == Case.id)
        .join(User, Case.submitted_by == User.id)
        .where(User.ps_id == ps_id, LienAccount.created_at >= start, LienAccount.created_at < end)
        .group_by(LienAccount.bank_name)
    )
    for bank, cnt, total in (await db.execute(lien_q)).all():
        bank = bank or "Unknown bank"
        row.lien_count += cnt
        row.lien_amount += _f(total)
        prev_c, prev_a = row.lien_by_bank.get(bank, (0, 0.0))
        row.lien_by_bank[bank] = (prev_c + cnt, prev_a + _f(total))

    # ── 5. Refunds ──
    refund_q = (
        select(
            func.count(),
            func.coalesce(func.sum(func.if_(Refund.refunded == "yes", 1, 0)), 0),
            func.coalesce(func.sum(func.if_(Refund.refunded == "yes", Refund.amount, 0)), 0),
        )
        .select_from(Refund)
        .join(Case, Refund.case_id == Case.id)
        .join(User, Case.submitted_by == User.id)
        .where(User.ps_id == ps_id, Refund.created_at >= start, Refund.created_at < end)
    )
    rcnt, rdone, ramt = (await db.execute(refund_q)).first() or (0, 0, 0)
    row.refunds_total = rcnt or 0
    row.refunds_done = int(rdone or 0)
    row.refunds_amount = _f(ramt)

    # ── 6. Mule reports (linked directly via submitted_by) ──
    mule_q = (
        select(func.count())
        .select_from(MuleReport)
        .join(User, MuleReport.submitted_by == User.id)
        .where(User.ps_id == ps_id, MuleReport.created_at >= start, MuleReport.created_at < end)
    )
    row.mule_reports_total = (await db.execute(mule_q)).scalar() or 0

    return row
