from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from utils.sanitize import strip_html


# Free-text fields that must never contain HTML/script — stripped server-side
_SANITIZED_TEXT_FIELDS = {
    # Case-level
    "facts", "fir_no", "petition_no",
    # Arrest / accused / accomplice
    "name", "address", "email", "aadhar", "pan", "statement",
    "where_met", "where_stayed", "interrogation_details",
    "photo_path", "mobile", "occupation", "remarks",
    # Petition
    "why_not", "nature",
    # Lien
    "account_no", "bank_name",
    # Unfreeze
    "crime_no",
    # Refund
    "victim_name", "crime_no_or_petition_no",
}


def _sanitize(cls, v):  # noqa: N805 — Pydantic validator signature
    return strip_html(v) if isinstance(v, str) else v


# ── Child Create schemas ──────────────────────────────────────────

class AccompliceCreate(BaseModel):
    where_met: Optional[str] = None
    where_stayed: Optional[str] = None
    interrogation_details: Optional[str] = None

    _sanitize_text = field_validator("where_met", "where_stayed", "interrogation_details")(_sanitize)


class AccusedDetailCreate(BaseModel):
    photo_path: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    occupation: Optional[str] = None
    remarks: Optional[str] = None

    _sanitize_text = field_validator("photo_path", "email", "mobile", "occupation", "remarks")(_sanitize)


class ArrestCreate(BaseModel):
    name: str
    address: Optional[str] = None
    email: Optional[str] = None
    aadhar: Optional[str] = None
    pan: Optional[str] = None
    date_of_arrest: Optional[date] = None
    statement: Optional[str] = None
    accomplices: List[AccompliceCreate] = Field(default_factory=list)
    accused_details: List[AccusedDetailCreate] = Field(default_factory=list)

    _sanitize_text = field_validator("name", "address", "email", "aadhar", "pan", "statement")(_sanitize)


class PetitionCreate(BaseModel):
    fir_registered: str = "no"
    why_not: Optional[str] = None
    nature: Optional[str] = None
    petition_type: str = "amount_lost"
    amount: Decimal = Decimal("0")

    _sanitize_text = field_validator("why_not", "nature")(_sanitize)


class LienAccountCreate(BaseModel):
    case_type: str = "FIR"
    account_no: str
    amount_lien_marked: Decimal = Decimal("0")
    layer: int = 1
    total_amount_in_account: Decimal = Decimal("0")
    bank_name: Optional[str] = None

    _sanitize_text = field_validator("account_no", "bank_name")(_sanitize)


class UnfreezeDetailCreate(BaseModel):
    unfreeze_type: str = "letter"
    crime_no: Optional[str] = None
    bank_name: Optional[str] = None
    account_no: Optional[str] = None
    amount: Decimal = Decimal("0")

    _sanitize_text = field_validator("crime_no", "bank_name", "account_no")(_sanitize)


class RefundCreate(BaseModel):
    refunded: str = "no"
    victim_name: Optional[str] = None
    amount: Decimal = Decimal("0")
    crime_no_or_petition_no: Optional[str] = None

    _sanitize_text = field_validator("victim_name", "crime_no_or_petition_no")(_sanitize)


# ── Case Create schema ────────────────────────────────────────────

class CaseCreate(BaseModel):
    fir_no: str = ""
    petition_no: Optional[str] = None
    registration_date: date | None = None
    case_type: str = "NCRP"
    crime_type: str = "Internet"
    facts: Optional[str] = None
    status: str = "draft"  # draft, submitted

    arrests: List[ArrestCreate] = Field(default_factory=list)
    petitions: List[PetitionCreate] = Field(default_factory=list)
    lien_accounts: List[LienAccountCreate] = Field(default_factory=list)
    unfreeze_details: List[UnfreezeDetailCreate] = Field(default_factory=list)
    refunds: List[RefundCreate] = Field(default_factory=list)

    _sanitize_text = field_validator("fir_no", "petition_no", "facts")(_sanitize)


# ── Child Response schemas ────────────────────────────────────────

class AccompliceResponse(BaseModel):
    id: str
    arrest_id: str
    where_met: Optional[str] = None
    where_stayed: Optional[str] = None
    interrogation_details: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class AccusedDetailResponse(BaseModel):
    id: str
    arrest_id: str
    photo_path: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    occupation: Optional[str] = None
    remarks: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class ArrestResponse(BaseModel):
    id: str
    case_id: str
    name: str
    address: Optional[str] = None
    email: Optional[str] = None
    aadhar: Optional[str] = None
    pan: Optional[str] = None
    date_of_arrest: Optional[date] = None
    created_at: Optional[str] = None
    accomplices: List[AccompliceResponse] = []
    accused_details: List[AccusedDetailResponse] = []

    class Config:
        from_attributes = True


class PetitionResponse(BaseModel):
    id: str
    case_id: str
    fir_registered: str
    why_not: Optional[str] = None
    nature: Optional[str] = None
    petition_type: str
    amount: float = 0
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class LienAccountResponse(BaseModel):
    id: str
    case_id: str
    case_type: str
    account_no: str
    amount_lien_marked: float = 0
    layer: int = 1
    total_amount_in_account: float = 0
    bank_name: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class UnfreezeDetailResponse(BaseModel):
    id: str
    case_id: str
    unfreeze_type: str
    crime_no: Optional[str] = None
    bank_name: Optional[str] = None
    account_no: Optional[str] = None
    amount: float = 0
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class RefundResponse(BaseModel):
    id: str
    case_id: str
    refunded: str
    victim_name: Optional[str] = None
    amount: float = 0
    crime_no_or_petition_no: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


# ── Case Response schemas ─────────────────────────────────────────

class CaseResponse(BaseModel):
    id: str
    unit_id: int
    fir_no: str
    petition_no: Optional[str] = None
    registration_date: date | None = None
    case_type: str
    crime_type: str
    facts: Optional[str] = None
    status: str = "draft"
    submitted_by: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    arrests: List[ArrestResponse] = []
    petitions: List[PetitionResponse] = []
    lien_accounts: List[LienAccountResponse] = []
    unfreeze_details: List[UnfreezeDetailResponse] = []
    refunds: List[RefundResponse] = []

    class Config:
        from_attributes = True


class CaseListItem(BaseModel):
    id: str
    unit_id: int
    fir_no: str
    petition_no: Optional[str] = None
    registration_date: date | None = None
    case_type: str
    crime_type: str
    facts: Optional[str] = None
    status: str = "draft"
    submitted_by: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    arrest_count: int = 0

    class Config:
        from_attributes = True
