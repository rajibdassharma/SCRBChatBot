from pydantic import BaseModel


class KpiSummary(BaseModel):
    total_cases: int = 0
    total_arrests: int = 0
    total_amount_lien_marked: float = 0
    total_amount_refunded: float = 0
    total_accounts_lien_marked: int = 0
    total_accounts_defreezed: int = 0
    units_submitted: int = 0
    units_total: int = 45


class UnitComparison(BaseModel):
    unit_name: str
    cases: int = 0
    arrests: int = 0
    amount_lien_marked: float = 0


class TrendPoint(BaseModel):
    report_date: str
    total_cases: int = 0
    total_arrests: int = 0
    total_petitions: int = 0


class SubmissionStatus(BaseModel):
    unit_id: int
    unit_name: str
    dsr_submitted: bool
    mule_submitted: bool
