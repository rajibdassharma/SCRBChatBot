"""
DailyWorkEntry — per-FIR, per-day investigation activity log.

One row = one PS's work on one FIR on one calendar date. Upsert
keyed on (unit_id, ps_id, fir_no, report_date), matching the DSR
pattern established in migration 008 (per-PS scoping is the VAPT
7.7/7.8 rule for every operator-created table since then).

The sheet is grouped into three colour sections (red / yellow /
green) — the columns below mirror that grouping so a reader who
opens the spreadsheet next to the code can trace fields 1-to-1.
`final_report` is nullable — case must stay unclosed until an A /
B / C letter is filed, so we can't force a value on every row.
"""
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Numeric,
    ForeignKey, UniqueConstraint, func,
)

from database import Base


class DailyWorkEntry(Base):
    __tablename__ = "daily_work_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    ps_id = Column(Integer, ForeignKey("police_stations.id"), nullable=False)
    report_date = Column(Date, nullable=False)
    fir_no = Column(String(50), nullable=False)

    # ── Red section — Notices ──────────────────────────────────
    notices_35_41a_count = Column(Integer, default=0, nullable=False)
    # 91/92/94 notices broken down by recipient (the four sub-columns
    # in the sheet's header).
    notices_91_92_94_banks = Column(Integer, default=0, nullable=False)
    notices_91_92_94_intermediary = Column(Integer, default=0, nullable=False)
    notices_91_92_94_account_holder = Column(Integer, default=0, nullable=False)
    notices_91_92_94_cdr_ipdr = Column(Integer, default=0, nullable=False)

    # ── Yellow section — Lien / Unlien ─────────────────────────
    lien_requests_count = Column(Integer, default=0, nullable=False)
    freeze_requests_count = Column(Integer, default=0, nullable=False)
    total_lien_amount = Column(Numeric(18, 2), default=0, nullable=False)
    unlien_requests_count = Column(Integer, default=0, nullable=False)
    defreeze_requests_count = Column(Integer, default=0, nullable=False)
    total_unlien_amount = Column(Numeric(18, 2), default=0, nullable=False)

    # ── Green section — Investigation Outcomes ─────────────────
    arrests_count = Column(Integer, default=0, nullable=False)
    statements_count = Column(Integer, default=0, nullable=False)
    # A = chargesheeted, B = false, C = undetected. Nullable until
    # the case is closed on this date.
    final_report = Column(String(1), nullable=True)

    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "unit_id", "ps_id", "fir_no", "report_date",
            name="uq_daily_work_unit_ps_fir_date",
        ),
    )
