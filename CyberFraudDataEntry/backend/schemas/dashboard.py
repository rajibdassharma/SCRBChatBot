from pydantic import BaseModel


class KpiSummary(BaseModel):
    total_cases: int = 0
    total_arrests: int = 0
    total_amount_lien_marked: float = 0
    total_amount_refunded: float = 0
    units_submitted: int = 0
    units_total: int = 45


class UnitComparison(BaseModel):
    unit_name: str
    cases: int = 0
    arrests: int = 0
    amount_lien_marked: float = 0
