from pydantic import BaseModel


class KpiSummary(BaseModel):
    total_cases: int = 0
    total_arrests: int = 0
    total_amount_lien_marked: float = 0
    total_amount_refunded: float = 0
    total_amount_defreezed: float = 0
    total_accounts_lien_marked: int = 0
    total_accounts_defreezed: int = 0
    units_submitted: int = 0
    units_total: int = 45


class UnitComparison(BaseModel):
    unit_id: int = 0
    unit_name: str
    cases: int = 0
    arrests: int = 0
    amount_lien_marked: float = 0
    # Number of distinct PSes that have assigned users in this district.
    # Drives the "drill into PSes" affordance — single-PS districts are
    # not worth a drill-down.
    ps_count: int = 0


class PsComparison(BaseModel):
    ps_name: str
    cases: int = 0


class TrendPoint(BaseModel):
    report_date: str
    total_cases: int = 0
    total_arrests: int = 0
    total_petitions: int = 0


class SubmissionStatus(BaseModel):
    unit_id: int
    unit_name: str
    # Cumulative cases + mule_reports made by this district up to `date`.
    entry_count: int = 0
    # Cumulative split — useful to see whether a PS is leaning more on case
    # work or mule-report work.
    cases_count: int = 0
    mule_count: int = 0
    # Activity on the selected date specifically — answers "are they
    # working today?" independent of the cumulative leaderboard.
    today_count: int = 0
    # Most recent date (cases OR mule_reports) the unit has entered
    # anything at all. None = never. ISO format (YYYY-MM-DD).
    last_entry_date: str | None = None
    # Whether the statutory daily report was filed for `date`.
    dsr_filed: bool = False


class QuietUnit(BaseModel):
    unit_id: int
    unit_name: str
    # None = the unit has never had any entry (case or mule report).
    days_silent: int | None = None
    last_entry_date: str | None = None


class TimeToArrestRow(BaseModel):
    unit_name: str
    avg_days: float = 0
    sample_size: int = 0


class BankSlaRow(BaseModel):
    bank: str
    avg_days: float = 0
    count: int = 0


# ── Investigation tab ──────────────────────────────────────────────────────

class RecurringAccount(BaseModel):
    account_no: str
    bank: str | None = None
    case_count: int = 0
    units_count: int = 0
    total_amount: float = 0


class BankConcentration(BaseModel):
    bank: str
    transaction_count: int = 0
    total_amount: float = 0


class AtmHotspot(BaseModel):
    location: str
    withdrawal_count: int = 0
    total_amount: float = 0


class LayerBucket(BaseModel):
    layer: int
    count: int = 0


class LienAccountAtLayer(BaseModel):
    """One frozen account at a specific layer, with the parent case context.
    Used by the layer-distribution drill-down."""
    lien_id: str
    account_no: str
    bank_name: str | None = None
    amount_lien_marked: float = 0
    layer: int = 0
    case_id: str
    fir_no: str | None = None
    petition_no: str | None = None
    registration_date: str | None = None
    district: str = ""
    ps_name: str | None = None


class AccountCaseDetail(BaseModel):
    """One case that a given account number is involved in, plus the
    matching lien_accounts row's bank/amount/layer."""
    case_id: str
    fir_no: str | None = None
    petition_no: str | None = None
    registration_date: str | None = None
    case_type: str | None = None
    crime_type: str | None = None
    status: str | None = None
    district: str = ""
    ps_name: str | None = None
    bank_name: str | None = None
    amount: float = 0
    layer: int | None = None
    lien_created_at: str | None = None


# ── Case detail (third drill-down level) ───────────────────────────────────

class ArrestSummary(BaseModel):
    name: str = ""
    date_of_arrest: str | None = None
    aadhar: str | None = None
    pan: str | None = None


class LienSummary(BaseModel):
    account_no: str = ""
    bank_name: str | None = None
    amount_lien_marked: float = 0
    layer: int | None = None


class PetitionSummary(BaseModel):
    petition_no: str | None = None
    nature: str | None = None
    petition_type: str | None = None
    amount: float = 0


class RefundSummary(BaseModel):
    victim_name: str | None = None
    amount: float = 0
    refunded: str | None = None


class CaseDetailFull(BaseModel):
    case_id: str
    fir_no: str | None = None
    petition_no: str | None = None
    registration_date: str | None = None
    case_type: str | None = None
    crime_type: str | None = None
    status: str | None = None
    facts: str | None = None
    district: str = ""
    ps_name: str | None = None
    arrests: list[ArrestSummary] = []
    lien_accounts: list[LienSummary] = []
    petitions: list[PetitionSummary] = []
    refunds: list[RefundSummary] = []


# ── Disposal & Trial tab ────────────────────────────────────────────────────

class DisposalSummary(BaseModel):
    detected: int = 0
    transferred: int = 0
    false_cases: int = 0
    undetected: int = 0


class TrialSummary(BaseModel):
    convicted: int = 0
    discharged: int = 0
    acquitted: int = 0
    abated: int = 0
    compounded: int = 0
    under_trial: int = 0


class PendingByYearRow(BaseModel):
    unit_name: str
    y2021: int = 0
    y2022: int = 0
    y2023: int = 0
    y2024: int = 0
    y2025: int = 0
    y2026: int = 0
