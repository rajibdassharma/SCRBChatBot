"""Pydantic schemas for the All Accounts feature.

Two write shapes:
  - AllAccountCreate  — POST body, no serial_no (server generates).
  - AllAccountUpdate  — PUT body, ditto (serial_no immutable after create).

One read shape:
  - AllAccountResponse — full detail with mule_herders inlined.
  - AllAccountListItem — trimmed row for the inbox / search table.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


AccountType = Literal["Victim", "Mule", "Non-Mule"]


# ── Mule herder (child) ─────────────────────────────────────────


class MuleHerderIn(BaseModel):
    """Input row for a mule herder — no id on create; id present on
    update means the row was loaded from the server (server-side we
    still full-replace the whole child collection to keep things
    simple)."""
    id: Optional[str] = None
    name: str = Field(min_length=1, max_length=200)
    address: Optional[str] = Field(default=None, max_length=2000)
    mobile_no: Optional[str] = Field(default=None, max_length=20)


class MuleHerderOut(BaseModel):
    id: str
    name: str
    address: Optional[str] = None
    mobile_no: Optional[str] = None


# ── AllAccount write shapes ─────────────────────────────────────


class AllAccountCreate(BaseModel):
    """POST body — everything the operator captures on Create. The
    server fills serial_no (per-PS max+1), unit_id + ps_id (from the
    JWT), submitted_by, and timestamps."""
    fir_no: Optional[str] = Field(default=None, max_length=50)
    ncrp_ack_no: Optional[str] = Field(default=None, max_length=60)

    account_no: str = Field(min_length=1, max_length=50)
    bank_name: str = Field(min_length=1, max_length=200)
    branch_name: Optional[str] = Field(default=None, max_length=200)
    branch_district: Optional[str] = Field(default=None, max_length=100)
    ifsc_code: Optional[str] = Field(default=None, max_length=20)

    account_holder_name: str = Field(min_length=1, max_length=200)
    kyc_address: Optional[str] = Field(default=None, max_length=5000)
    kyc_mobile: Optional[str] = Field(default=None, max_length=20)
    id_photo_path: Optional[str] = Field(default=None, max_length=500)

    account_type: AccountType
    # Only meaningful when account_type == 'Mule'. If [] and Victim,
    # server ignores. If populated on a Victim, server rejects with 422.
    mule_herders: List[MuleHerderIn] = []

    @field_validator("mule_herders")
    @classmethod
    def _mule_herders_only_for_mule(cls, v, info):
        # This runs before account_type is guaranteed to be set on the
        # dict; the server-side route handler enforces the invariant
        # explicitly after validation for a clearer error message.
        return v


class AllAccountUpdate(AllAccountCreate):
    """PUT body — same shape as create. serial_no is not editable."""


# ── AllAccount read shapes ──────────────────────────────────────


class AllAccountResponse(BaseModel):
    id: str
    unit_id: int
    ps_id: int
    serial_no: int

    fir_no: Optional[str] = None
    ncrp_ack_no: Optional[str] = None

    account_no: str
    bank_name: str
    branch_name: Optional[str] = None
    branch_district: Optional[str] = None
    ifsc_code: Optional[str] = None

    account_holder_name: str
    kyc_address: Optional[str] = None
    kyc_mobile: Optional[str] = None
    id_photo_path: Optional[str] = None

    account_type: str
    mule_herders: List[MuleHerderOut] = []

    submitted_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class AllAccountListItem(BaseModel):
    """One row on the search / list view — enough to scan + click into."""
    id: str
    serial_no: int
    account_no: str
    bank_name: str
    account_holder_name: str
    account_type: str
    fir_no: Optional[str] = None
    ncrp_ack_no: Optional[str] = None
    created_at: datetime
