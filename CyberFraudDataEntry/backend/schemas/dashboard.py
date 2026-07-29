from datetime import date

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


# ── Accounts dashboard (2026-07-18) ─────────────────────────────
# Same shape as DSR Overview — headline KPI cards + per-PS
# comparison table — but populated from all_accounts.


class AccountsKpiSummary(BaseModel):
    total_accounts: int = 0
    victim_accounts: int = 0
    mule_accounts: int = 0
    non_mule_accounts: int = 0
    # Mule accounts whose bank branch is in Karnataka -- a subset of
    # mule_accounts, surfaces the in-state exposure separately from
    # cross-border ones (2026-07-27).
    karnataka_mule_accounts: int = 0
    unique_banks: int = 0
    unique_mule_herders: int = 0
    accounts_with_photo: int = 0
    units_submitted: int = 0
    units_total: int = 45


class AccountsPsComparison(BaseModel):
    """One row per PS on the accounts comparison table. Mirrors the
    shape of DSR's UnitComparison — a PS scope is finer than a unit
    scope (Bangalore City has many PSes), so we group by PS directly.

    `yesterday_count` is the number of accounts created on the calendar
    day BEFORE the request's `date` — surfaces the last 24-hour drip
    beside the cumulative Total (2026-07-24)."""
    unit_id: int
    unit_name: str
    ps_id: int
    ps_name: str
    total: int = 0
    yesterday_count: int = 0
    victims: int = 0
    mules: int = 0
    non_mules: int = 0


class AccountsBankConcentration(BaseModel):
    """One row on the Top Banks chart — how many All Accounts records
    reference this bank. Powers the Dashboard Overview insight panel."""
    bank_name: str
    total: int = 0
    victims: int = 0
    mules: int = 0
    non_mules: int = 0


class AccountsDailyPoint(BaseModel):
    """One point on the Accounts daily-growth line chart. `count` is the
    number of accounts created on that day (per-day new rows, not
    cumulative — the chart draws deltas, not the running total)."""
    day: date
    count: int = 0


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
    # Rolled up at PS level — most districts have one CEN PS, but Bangalore
    # City has multiple and each needs its own row.
    ps_id: int = 0
    ps_name: str = ""
    # Cumulative cases + petitions + mule_reports made by this PS up to
    # `date`. Petitions count rows in the `petitions` child table, not
    # cases where case_type='Petition' — same definition the DSR
    # aggregator uses, so dashboard and DSR PDF stay reconciled.
    entry_count: int = 0
    # Cumulative split — useful to see whether a PS is leaning more on case
    # work, petition intake, or mule-report work.
    cases_count: int = 0
    petitions_count: int = 0
    mule_count: int = 0
    # Most recent date the PS has done anything at all — cases,
    # mule_reports, OR a NIL declaration. NIL is treated as a valid
    # entry for this purpose, so a PS that only ever declares NIL
    # never shows "Never". None = never (no entry AND no NIL). ISO
    # format (YYYY-MM-DD).
    last_entry_date: str | None = None
    # Whether the statutory daily report was filed for `date` for this PS's
    # district. DSR is a district-level concept, so all PS rows in the same
    # district share the same flag.
    dsr_filed: bool = False
    # Whether the PS explicitly declared "no activity" for `date` (the
    # target date only). Used to render the green "NIL declared" pill in
    # the Total column when entry_count is 0.
    nil_declared: bool = False
    nil_declared_by_name: str | None = None
    # Cumulative NIL declarations by this PS up to `date`. Rendered as
    # the "NIL" column on the Submission Status table.
    nil_count: int = 0


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


class AccountsLayerDistribution(BaseModel):
    """Layer 1..15 distribution of all_accounts split by branch state.
    Karnataka bucket = branch_state = 'Karnataka'. Rest bucket = every
    other value INCLUDING NULL (legacy pre-migration-012 rows that
    don't have a confirmed state count as 'not confirmed KA' = Rest).

    Only accounts with a non-NULL layer are in the ka / rest arrays.
    unknown_layer_ka + unknown_layer_rest count accounts with a NULL
    layer so the frontend can surface them in the chart subtitle."""
    ka: list[LayerBucket] = []
    rest: list[LayerBucket] = []
    unknown_layer_ka: int = 0
    unknown_layer_rest: int = 0


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


# ── FIR Dashboard (DSR module) ─────────────────────────────────────
# Per-PS performance rollup. One row per active (district, PS) pair
# with the count of FIRs whose registration_date falls in the window.
# Sourced entirely from `cases` — no derived metrics from arrest /
# petition / lien tables, per the 2026-07-22 spec ("Select only from
# the fields that are there in the Case Detail entry").


class FirPsPerformanceRow(BaseModel):
    unit_id: int
    district: str
    ps_id: int
    ps_name: str
    fir_count: int = 0
    # New FIRs registered YESTERDAY (server today − 1 day), independent
    # of the from/to window. Surfaces "last 24h" pulse next to the
    # cumulative Total column — added 2026-07-25.
    yesterday_count: int = 0
