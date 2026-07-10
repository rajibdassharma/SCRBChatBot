from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Numeric,
    ForeignKey, UniqueConstraint, func,
)

from database import Base


class DsrEntry(Base):
    __tablename__ = "dsr_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    # DSR became a per-PS filing in migration 008 (2026-07-08). Before
    # that the uniqueness key was (unit_id, report_date) — one DSR per
    # district per date — and this column didn't exist.
    ps_id = Column(Integer, ForeignKey("police_stations.id"), nullable=False)
    report_date = Column(Date, nullable=False)

    # Group: Cases & Petitions
    cases = Column(Integer, default=0)
    petitions = Column(Integer, default=0)
    details_of_arrest = Column(Integer, default=0)

    # Group: Amount Lien Marked
    case_type = Column(String(20), nullable=True)  # FIR or NCRP
    cumulative_amount_lien_marked = Column(Numeric(18, 2), default=0)
    cumulative_accounts_lien_marked = Column(Integer, default=0)
    cumulative_accounts_defreezed = Column(Integer, default=0)

    # Group: Amount Refunded
    amount_refunded_to_victim = Column(Numeric(18, 2), default=0)

    # Group: UI Cases Pending by year
    ui_cases_pending_2021 = Column(Integer, default=0)
    ui_cases_pending_2022 = Column(Integer, default=0)
    ui_cases_pending_2023 = Column(Integer, default=0)
    ui_cases_pending_2024 = Column(Integer, default=0)
    ui_cases_pending_2025 = Column(Integer, default=0)
    ui_cases_pending_2026 = Column(Integer, default=0)

    # Group: Cases Disposed (since 1 Jan 2026)
    disposed_detected_chargesheeted = Column(Integer, default=0)
    disposed_transferred = Column(Integer, default=0)
    disposed_false = Column(Integer, default=0)
    disposed_undetected = Column(Integer, default=0)

    # Group: Trial Status (from 1 Jan 2026)
    trial_convicted = Column(Integer, default=0)
    trial_discharged = Column(Integer, default=0)
    trial_acquitted = Column(Integer, default=0)
    trial_abated = Column(Integer, default=0)
    trial_compounded = Column(Integer, default=0)
    trial_ut = Column(Integer, default=0)

    # Metadata
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("unit_id", "ps_id", "report_date", name="uq_dsr_unit_ps_date"),
    )
