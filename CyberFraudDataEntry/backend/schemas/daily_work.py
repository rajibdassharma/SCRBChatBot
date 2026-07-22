"""Pydantic schemas for daily-work-done entries.

Field validation:
 - Every count is `ge=0` — negative counts are meaningless here.
 - `fir_no` is required, trimmed, and length-bounded — same shape as
   the FIR column on Cases.
 - `final_report` is the enum A / B / C or None.
 - `case_type`-style free-text fields don't exist on this form, so we
   don't need the DSR-style HTML sanitize; the only string on this
   sheet is `fir_no`, which is character-restricted below.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from utils.validators import validate_fir_no as _validate_fir_no


FinalReport = Literal["A", "B", "C"]


class DailyWorkCreate(BaseModel):
    report_date: date
    fir_no: str = Field(..., min_length=1, max_length=50)

    # Red — Notices
    notices_35_41a_count: int = Field(default=0, ge=0)
    notices_91_92_94_banks: int = Field(default=0, ge=0)
    notices_91_92_94_intermediary: int = Field(default=0, ge=0)
    notices_91_92_94_account_holder: int = Field(default=0, ge=0)
    notices_91_92_94_cdr_ipdr: int = Field(default=0, ge=0)

    # Yellow — Lien / Unlien
    lien_requests_count: int = Field(default=0, ge=0)
    freeze_requests_count: int = Field(default=0, ge=0)
    total_lien_amount: Decimal = Field(default=Decimal("0"), ge=0)
    unlien_requests_count: int = Field(default=0, ge=0)
    defreeze_requests_count: int = Field(default=0, ge=0)
    total_unlien_amount: Decimal = Field(default=Decimal("0"), ge=0)

    # Green — Investigation Outcomes
    arrests_count: int = Field(default=0, ge=0)
    statements_count: int = Field(default=0, ge=0)
    final_report: FinalReport | None = None

    # Format-check + trim in one shot via the shared validator. See
    # feedback memory `fir-no-format-nnn-yyyy` for the project-wide
    # rule. min_length=1 above already rejects the empty case before
    # this fires — the validator just handles trim + NNN/YYYY check.
    _check_fir_no = field_validator("fir_no")(_validate_fir_no)


class DailyWorkResponse(DailyWorkCreate):
    id: int
    unit_id: int
    ps_id: int
    unit_name: str | None = None
    submitted_by: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True
