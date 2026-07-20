"""AllAccount — the "All Accounts" feature (2026-07-18).

One row per bank / wallet account that a KA CEN PS is investigating,
be it a victim's own account or a suspected mule account. Broader
than the mule-report + lien-account feature because it captures
victim accounts too.

Per-PS scoping (VAPT 7.7 + 7.8) — every row carries `unit_id` +
`ps_id`, and the same `check_record_access` helper the rest of the
app uses is applied on every detail/edit endpoint.

`serial_no` is auto-generated at create time as `MAX(serial_no) + 1`
scoped to the (unit_id, ps_id) pair — a per-PS counter that starts
at 1 and never rolls back. Unique constraint enforces the invariant
at the DB level in case two parallel requests race for the same
number.
"""
import uuid

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from database import Base


# Non-Mule = an account under investigation that has NOT been
# confirmed as a mule (the operator either still needs to verify, or
# has verified it isn't one). Mule Herder rows only apply to 'Mule'.
ACCOUNT_TYPES = frozenset({"Victim", "Mule", "Non-Mule"})


class AllAccount(Base):
    __tablename__ = "all_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Scoping (per-PS ownership) — same shape as Case.
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    ps_id = Column(Integer, ForeignKey("police_stations.id"), nullable=False)

    # Auto-incremented per (unit_id, ps_id) at create time. Unique
    # within a PS's namespace; different PSes get their own counters.
    serial_no = Column(Integer, nullable=False)

    # Case / complaint linkage — either FIR-side or NCRP-side (or
    # both). Both nullable — an account can be under investigation
    # before any formal case/complaint is opened.
    fir_no = Column(String(50), nullable=True)
    ncrp_ack_no = Column(String(60), nullable=True)

    # Bank details.
    account_no = Column(String(50), nullable=False)
    bank_name = Column(String(200), nullable=False)
    branch_name = Column(String(200), nullable=True)
    # Karnataka district the branch is located in. Nullable because
    # existing rows predate the field; the entry form treats it as
    # optional so operators can save a draft before confirming.
    branch_district = Column(String(100), nullable=True)
    ifsc_code = Column(String(20), nullable=True)

    # Account holder identity.
    account_holder_name = Column(String(200), nullable=False)
    kyc_address = Column(Text, nullable=True)
    kyc_mobile = Column(String(20), nullable=True)
    # Path to the uploaded ID document photo/scan
    # (Aadhaar/PAN/passport etc.) — filesystem path under /uploads.
    # Reuses the existing POST /api/v1/uploads/photo endpoint.
    id_photo_path = Column(String(500), nullable=True)

    # Victim vs Mule (see ACCOUNT_TYPES).
    account_type = Column(String(20), nullable=False)

    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    mule_herders = relationship(
        "AllAccountMuleHerder",
        back_populates="account",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "unit_id", "ps_id", "serial_no",
            name="uq_all_account_ps_serial",
        ),
    )
