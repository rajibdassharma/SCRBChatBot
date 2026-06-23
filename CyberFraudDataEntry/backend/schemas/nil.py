from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class NilDeclarationCreate(BaseModel):
    """Mark today (or another date) as NIL for the caller's PS.
    Defaults to today if no date provided."""
    nil_date: Optional[date] = None
    reason: Optional[str] = Field(default=None, max_length=255)


class NilDeclarationResponse(BaseModel):
    id: str
    unit_id: int
    ps_id: int
    declared_by: int
    declared_by_name: Optional[str] = None
    nil_date: date
    reason: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True
