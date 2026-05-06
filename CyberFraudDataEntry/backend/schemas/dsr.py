from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from utils.sanitize import strip_html


def _sanitize(cls, v):  # noqa: N805 - Pydantic validator signature
    return strip_html(v) if isinstance(v, str) else v


class DsrCreate(BaseModel):
    report_date: date

    # Cases & Petitions
    cases: int = Field(default=0, ge=0)
    petitions: int = Field(default=0, ge=0)
    details_of_arrest: int = Field(default=0, ge=0)

    # Amount Lien Marked
    case_type: str | None = None

    # VAPT 7.5 (rec #5 - "review all modules"): case_type is the only
    # free-text field on the DSR. Sanitize to defend against stored
    # XSS from any future endpoint that renders it.
    _sanitize_text = field_validator("case_type")(_sanitize)
    cumulative_amount_lien_marked: Decimal = Field(default=Decimal("0"), ge=0)
    cumulative_accounts_lien_marked: int = Field(default=0, ge=0)
    cumulative_accounts_defreezed: int = Field(default=0, ge=0)

    # Amount Refunded
    amount_refunded_to_victim: Decimal = Field(default=Decimal("0"), ge=0)

    # UI Cases Pending
    ui_cases_pending_2021: int = Field(default=0, ge=0)
    ui_cases_pending_2022: int = Field(default=0, ge=0)
    ui_cases_pending_2023: int = Field(default=0, ge=0)
    ui_cases_pending_2024: int = Field(default=0, ge=0)
    ui_cases_pending_2025: int = Field(default=0, ge=0)
    ui_cases_pending_2026: int = Field(default=0, ge=0)

    # Cases Disposed
    disposed_detected_chargesheeted: int = Field(default=0, ge=0)
    disposed_transferred: int = Field(default=0, ge=0)
    disposed_false: int = Field(default=0, ge=0)
    disposed_undetected: int = Field(default=0, ge=0)

    # Trial Status
    trial_convicted: int = Field(default=0, ge=0)
    trial_discharged: int = Field(default=0, ge=0)
    trial_acquitted: int = Field(default=0, ge=0)
    trial_abated: int = Field(default=0, ge=0)
    trial_compounded: int = Field(default=0, ge=0)
    trial_ut: int = Field(default=0, ge=0)


class DsrResponse(DsrCreate):
    id: int
    unit_id: int
    unit_name: str | None = None
    submitted_by: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True
