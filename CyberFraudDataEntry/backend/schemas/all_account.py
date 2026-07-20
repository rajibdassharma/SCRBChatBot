"""Pydantic schemas for the All Accounts feature.

Two write shapes:
  - AllAccountCreate  — POST body, no serial_no (server generates).
  - AllAccountUpdate  — PUT body, ditto (serial_no immutable after create).

One read shape:
  - AllAccountResponse — full detail with mule_herders inlined.
  - AllAccountListItem — trimmed row for the inbox / search table.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


AccountType = Literal["Victim", "Mule", "Non-Mule"]


# ── Shared field validators ─────────────────────────────────────
# Applied identically at the entry form (UX) and here (defence in
# depth). Rules confirmed with operators 2026-07-20.

_NUMERIC = re.compile(r"^\d+$")
_FIR_NO = re.compile(r"^\d{4}/\d{4}$")


def _validate_fir_no(v: Optional[str]) -> Optional[str]:
    """FIR No must be XXXX/XXXX (4 numeric digits, slash, 4 numeric
    digits) so operators enter 0001/2026, not 1/2026. Blank/None is
    allowed — the field is optional."""
    if v is None:
        return None
    t = v.strip()
    if not t:
        return None
    if not _FIR_NO.match(t):
        raise ValueError("FIR No must be in the format XXXX/XXXX (e.g. 0001/2026).")
    return t


def _validate_account_no(v: str) -> str:
    """Bank account number rules:
      - all numeric (digits only)
      - 11 to 18 digits
      - not a trivial run of a single digit (all-zeros / all-nines)
    """
    t = (v or "").strip()
    if not t:
        raise ValueError("Account No is required.")
    if not _NUMERIC.match(t):
        raise ValueError("Account No must be all numeric digits.")
    if len(t) < 11 or len(t) > 18:
        raise ValueError("Account No must be between 11 and 18 digits.")
    if t == "0" * len(t):
        raise ValueError("Account No cannot be all zeros.")
    if t == "9" * len(t):
        raise ValueError("Account No cannot be all nines.")
    return t


def _validate_mobile(v: Optional[str], *, label: str = "Mobile No") -> Optional[str]:
    """Indian-format mobile rules (optional field — None / '' passes):
      - all numeric (digits only)
      - exactly 10 digits
      - not 0000000000 / not 9999999999
    """
    if v is None:
        return None
    t = v.strip()
    if not t:
        return None
    if not _NUMERIC.match(t):
        raise ValueError(f"{label} must be all numeric digits.")
    if len(t) != 10:
        raise ValueError(f"{label} must be exactly 10 digits.")
    if t in ("0000000000", "9999999999"):
        raise ValueError(f"{label} cannot be all zeros or all nines.")
    return t


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

    @field_validator("mobile_no")
    @classmethod
    def _v_mobile_no(cls, v):
        return _validate_mobile(v, label="Mule Herder Mobile No")


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
    account_statement_path: Optional[str] = Field(default=None, max_length=500)

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

    @field_validator("account_no")
    @classmethod
    def _v_account_no(cls, v: str) -> str:
        return _validate_account_no(v)

    @field_validator("kyc_mobile")
    @classmethod
    def _v_kyc_mobile(cls, v):
        return _validate_mobile(v, label="Mobile No")

    @field_validator("fir_no")
    @classmethod
    def _v_fir_no(cls, v):
        return _validate_fir_no(v)


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
    account_statement_path: Optional[str] = None

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
