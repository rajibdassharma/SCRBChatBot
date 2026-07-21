"""Pydantic schemas for the Portals DSR feature.

Shapes:
  - PortalsDsrCreate / PortalsDsrUpdate  — write bodies (all metric
    fields default to 0 so operators can save partial drafts).
  - PortalsDsrResponse                    — single-row read.
  - PortalsDsrListItem                    — trimmed row for the list
    view (id + who/when + status + total).
  - PortalsDsrKpiSummary                  — grand totals across
    scope + date range.
  - PortalsDsrPsComparison                — one row per PS with all 25
    metric totals aggregated across submissions.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


PortalsDsrStatus = Literal["draft", "submitted"]


class PortalsDsrCreate(BaseModel):
    """POST body — server fills unit_id + ps_id from JWT, submitted_by,
    timestamps. `report_date` defaults to today if the client omits it.
    All metric fields default to 0 so a partial-draft tab-by-tab flow
    works without every field being present."""
    report_date: date
    status: PortalsDsrStatus = "draft"

    # NCRP (3)
    ncrp_received: int = Field(default=0, ge=0)
    ncrp_disposed: int = Field(default=0, ge=0)
    ncrp_pending: int = Field(default=0, ge=0)

    # Samanvaya (6)
    samanvaya_request_received: int = Field(default=0, ge=0)
    samanvaya_actions: int = Field(default=0, ge=0)
    samanvaya_action_pending: int = Field(default=0, ge=0)
    samanvaya_request_sent: int = Field(default=0, ge=0)
    samanvaya_reply_received: int = Field(default=0, ge=0)
    samanvaya_replies_pending: int = Field(default=0, ge=0)

    # Sahayog (3)
    sahayog_unlawful_content_removal: int = Field(default=0, ge=0)
    sahayog_intermediary_requests: int = Field(default=0, ge=0)
    sahayog_crypto_requests: int = Field(default=0, ge=0)

    # GRM (3)
    grm_request_received: int = Field(default=0, ge=0)
    grm_action: int = Field(default=0, ge=0)
    grm_pending: int = Field(default=0, ge=0)

    # MRM (3)
    mrm_request_received: int = Field(default=0, ge=0)
    mrm_action: int = Field(default=0, ge=0)
    mrm_pending: int = Field(default=0, ge=0)

    # Bharatpol (1)
    bharatpol_request_received: int = Field(default=0, ge=0)

    # OCWC (3)
    ocwc_received: int = Field(default=0, ge=0)
    ocwc_disposed: int = Field(default=0, ge=0)
    ocwc_pending: int = Field(default=0, ge=0)

    # NCMEC Tipline (3)
    ncmec_received: int = Field(default=0, ge=0)
    ncmec_disposed: int = Field(default=0, ge=0)
    ncmec_pending: int = Field(default=0, ge=0)


class PortalsDsrUpdate(PortalsDsrCreate):
    """PUT body — same shape as Create. unit_id/ps_id are immutable."""


class PortalsDsrResponse(PortalsDsrCreate):
    id: str
    unit_id: int
    ps_id: int
    submitted_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class PortalsDsrListItem(BaseModel):
    """One row on the update / history list. Total is the sum of all
    25 metrics on this single entry — a quick eyeball metric to spot
    zero-only rows."""
    id: str
    report_date: date
    status: str
    total: int
    submitted_by: Optional[int] = None
    created_at: datetime


# ── Dashboard shapes ─────────────────────────────────────────────


class PortalsDsrKpiSummary(BaseModel):
    """Grand totals across the caller's scope + date range.
    Each metric field is a SUM across every submitted row that falls
    in the window. Draft entries are EXCLUDED so the KPIs never
    inflate on in-progress work."""
    total_entries: int = 0

    # NCRP
    ncrp_received: int = 0
    ncrp_disposed: int = 0
    ncrp_pending: int = 0

    # Samanvaya
    samanvaya_request_received: int = 0
    samanvaya_actions: int = 0
    samanvaya_action_pending: int = 0
    samanvaya_request_sent: int = 0
    samanvaya_reply_received: int = 0
    samanvaya_replies_pending: int = 0

    # Sahayog
    sahayog_unlawful_content_removal: int = 0
    sahayog_intermediary_requests: int = 0
    sahayog_crypto_requests: int = 0

    # GRM
    grm_request_received: int = 0
    grm_action: int = 0
    grm_pending: int = 0

    # MRM
    mrm_request_received: int = 0
    mrm_action: int = 0
    mrm_pending: int = 0

    # Bharatpol
    bharatpol_request_received: int = 0

    # OCWC
    ocwc_received: int = 0
    ocwc_disposed: int = 0
    ocwc_pending: int = 0

    # NCMEC Tipline
    ncmec_received: int = 0
    ncmec_disposed: int = 0
    ncmec_pending: int = 0

    units_submitted: int = 0
    units_total: int = 0


class PortalsDsrPsComparison(BaseModel):
    """One row per PS. `total` is a coarse ranking metric — sum of
    every counter this PS has submitted in the window."""
    unit_id: int
    unit_name: str
    ps_id: int
    ps_name: str
    entries: int = 0
    total: int = 0
