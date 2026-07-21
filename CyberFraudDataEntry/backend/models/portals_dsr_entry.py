"""PortalsDsrEntry — the "Portals DSR" feature (2026-07-21).

One row per PS submission of daily counters for 8 external portals
(NCRP, Samanvaya, Sahayog, GRM, MRM, Bharatpol, OCWC, NCMEC Tipline).

Multiple rows per (unit_id, ps_id, report_date) are legal — operators
enter shift-based batches through the day. Dashboard SUM-aggregates
across all entries for a date range so the totals reflect every batch.
No unique constraint on (unit_id, ps_id, report_date).

Per-PS scoping (VAPT 7.7 + 7.8) — every row carries unit_id + ps_id
and the same check_record_access helper the rest of the app uses is
applied on every detail/edit endpoint.

Column layout follows the paper form the operators use today (see
migration 013 for the definitive list, grouped by portal).
"""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Date, func

from database import Base


PORTAL_STATUSES = frozenset({"draft", "submitted"})


class PortalsDsrEntry(Base):
    __tablename__ = "portals_dsr_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Scoping (per-PS ownership) — matches Case + AllAccount pattern.
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    ps_id = Column(Integer, ForeignKey("police_stations.id"), nullable=False)

    # Calendar day this entry counts against. Different from created_at
    # (submission timestamp) so dashboards can aggregate by report date
    # regardless of when the operator actually got round to entering.
    report_date = Column(Date, nullable=False)

    status = Column(String(20), nullable=False, default="draft")

    # ── Portal metric columns — mirror the paper form, grouped by portal.
    # All INT NOT NULL DEFAULT 0 so a blank field means "zero" for the
    # aggregation and the operator never has to explicitly type zeros.

    # NCRP (3)
    ncrp_received = Column(Integer, nullable=False, default=0)
    ncrp_disposed = Column(Integer, nullable=False, default=0)
    ncrp_pending = Column(Integer, nullable=False, default=0)

    # Samanvaya (6) — coordination portal, both incoming + outgoing.
    # Incoming side: Request Received + Actions + Action Pending (separate).
    # Outgoing side ends with Replies Pending (not generic Pending).
    samanvaya_request_received = Column(Integer, nullable=False, default=0)
    samanvaya_actions = Column(Integer, nullable=False, default=0)
    samanvaya_action_pending = Column(Integer, nullable=False, default=0)
    samanvaya_request_sent = Column(Integer, nullable=False, default=0)
    samanvaya_reply_received = Column(Integer, nullable=False, default=0)
    samanvaya_replies_pending = Column(Integer, nullable=False, default=0)

    # Sahayog (3) — content-removal portal
    sahayog_unlawful_content_removal = Column(Integer, nullable=False, default=0)
    sahayog_intermediary_requests = Column(Integer, nullable=False, default=0)
    sahayog_crypto_requests = Column(Integer, nullable=False, default=0)

    # GRM (3) — Action + Pending split into two columns per operator ask.
    grm_request_received = Column(Integer, nullable=False, default=0)
    grm_action = Column(Integer, nullable=False, default=0)
    grm_pending = Column(Integer, nullable=False, default=0)

    # MRM (3) — same shape as GRM.
    mrm_request_received = Column(Integer, nullable=False, default=0)
    mrm_action = Column(Integer, nullable=False, default=0)
    mrm_pending = Column(Integer, nullable=False, default=0)

    # Bharatpol (1) — only Requests Received captured on the paper form.
    bharatpol_request_received = Column(Integer, nullable=False, default=0)

    # OCWC (3)
    ocwc_received = Column(Integer, nullable=False, default=0)
    ocwc_disposed = Column(Integer, nullable=False, default=0)
    ocwc_pending = Column(Integer, nullable=False, default=0)

    # NCMEC (Tipline) (3)
    ncmec_received = Column(Integer, nullable=False, default=0)
    ncmec_disposed = Column(Integer, nullable=False, default=0)
    ncmec_pending = Column(Integer, nullable=False, default=0)

    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
