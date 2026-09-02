from datetime import date
from typing import List, Optional

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


class AccountsGeoRegion(BaseModel):
    """One geographic region on the Account Details map view (2026-07-31).

    `region` is the raw grouping value, NOT a validated enum:

      - scope=state      -> all_accounts.branch_state (free-text VARCHAR;
                            the picklist is enforced only in the frontend,
                            so legacy rows may hold anything)
      - scope=district   -> all_accounts.branch_district (Karnataka only)
      - scope=reporting  -> police_stations.district_name of the PS that
                            OWNS the row — a different question from where
                            the branch sits, and unlike branch_* it is
                            never NULL.

    Rows with a NULL/blank grouping value collapse into a single entry
    with region="" rather than being dropped. That bucket is the honest
    measure of how incomplete branch_state / branch_district coverage
    still is (both columns arrived in migrations 010/012, well after
    data entry began), and the map surfaces it explicitly instead of
    quietly under-counting regions."""
    region: str = ""
    total: int = 0
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


class FirTraceCase(BaseModel):
    """Case metadata shown in the header of the FIR Trace view.
    Populated from the `cases` table if a case exists for the FIR;
    None if only mule-report / all-accounts references exist."""
    case_id: Optional[str] = None
    fir_no: str
    unit_name: Optional[str] = None
    ps_name: Optional[str] = None
    registration_date: Optional[date] = None
    case_type: Optional[str] = None
    crime_type: Optional[str] = None
    victim_name: Optional[str] = None
    amount_lost: float = 0


class FirTraceAccount(BaseModel):
    """One account touching the FIR, from any of the 5 source tables.
    `source` tags where it came from so the operator can trace back
    to the entry point that owns the row."""
    source: str          # all_accounts / lien_accounts / victim_accounts / accused_accounts / money_transfer
    layer: Optional[int] = None
    account_no: Optional[str] = None
    account_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    branch_name: Optional[str] = None
    branch_state: Optional[str] = None
    ifsc_code: Optional[str] = None
    amount: float = 0        # normalised across sources (amount_lien_marked / amount_transferred / transaction_amount)
    account_type: Optional[str] = None  # Victim / Mule / Non-Mule -- only populated for all_accounts source
    #: Present only for rows sourced from all_accounts -- the other four
    #: source tables carry no account id to join on. Everything below is
    #: therefore zero for those rows, which is a gap in the source data
    #: rather than a statement that the account is clean.
    account_id: Optional[str] = None
    #: Transactions naming a crypto exchange or asset. A LEAD, not proof:
    #: see analysis/parsers/crypto.py for the false positives this has
    #: already produced on real narrations.
    crypto_txns: int = 0
    crypto_exchanges: List[str] = []
    #: Chain-passed rows only, matching every other money figure here.
    crypto_debit: float = 0
    #: Transfers to mule accounts that are NOT part of this FIR. Counted
    #: rather than drawn -- each one is a thread leading out of this case
    #: file, and the count is what tells an officer to go looking.
    external_links: int = 0


class FirTraceFlow(BaseModel):
    """One account-to-account transfer inside this FIR's account set.

    Read from mule_account_link, which is built by matching counterparty
    numbers in parsed statements against known mule accounts. This is
    the first edge on this screen that is EVIDENCE rather than layout:
    the layer columns say how far from the victim an account sits, but
    they never said who paid whom. An arrow here means one account's own
    bank statement names the other's account number.

    Only drawn between two accounts already in the trace. A link to an
    account outside this FIR is counted on the account instead -- drawing
    it would put a node on screen that the officer did not ask to see
    and that this FIR's case file does not cover."""
    src_account_id: str
    dst_account_id: str
    txns: int = 0
    amount: float = 0
    cross_fir: bool = False


class AccountsFirTrace(BaseModel):
    """Deep Analysis: everything the DB knows about one FIR, joined
    from the 5 account/transfer tables. Foundation for the layered
    accounts table + money-flow-per-layer chart on the Deep Analysis
    tab. super_admin only."""
    fir_no: str
    case: Optional[FirTraceCase] = None
    accounts: List[FirTraceAccount] = []
    #: Drawable transfers between two accounts in `accounts`.
    flows: List[FirTraceFlow] = []
    #: The same case drawn as a NETWORK rather than as layer columns.
    #:
    #: One row per account in this FIR, each carrying EVERY link it has
    #: -- including links to accounts that are not part of this FIR.
    #: `flows` above deliberately holds only transfers with both ends
    #: inside the case, which is what the layer table needs; that is
    #: also why it shows ~20% of the money. At layer 1, 77% of onward
    #: payments go to accounts nobody recorded under this FIR, and those
    #: are the hops an investigator is actually chasing.
    #:
    #: Deliberately MuleNetworkRow, the same shape the Mule Network tab
    #: consumes, so both screens draw through one component and an
    #: account looks the same wherever it appears.
    network: List["MuleNetworkRow"] = []
    warnings: List[str] = []


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


class FirDailyPoint(BaseModel):
    """One point on the FIR Dashboard growth line.

    `day` is the REGISTRATION date, not created_at — matching the
    per-PS table on the same page, so a back-dated entry lands on the
    day the FIR was actually registered and the line total always
    equals the table's grand total. Days with no FIRs come back with
    count = 0 so the axis stays continuous.

    Split by cases.is_financial so the chart can draw one line or two
    without a second request: picking Financial / Non-Financial in the
    UI is then a render choice, not a refetch."""
    day: date
    count: int = 0
    financial: int = 0
    non_financial: int = 0


class DuplicateIdMember(BaseModel):
    """One account inside a duplicate-ID cluster."""
    account_id: str
    account_holder_name: Optional[str] = None
    account_no: Optional[str] = None
    fir_no: Optional[str] = None
    account_type: Optional[str] = None
    district: Optional[str] = None
    ps_name: Optional[str] = None
    bank_name: Optional[str] = None


class DuplicateIdCluster(BaseModel):
    """A set of accounts whose uploaded ID photo is the SAME FILE.

    `fingerprint` is the SHA-256 of the file bytes — not anything read
    out of the picture. No name, no number, no date of birth is
    extracted at any point.

    SHA-256 and not a perceptual hash, and the distinction is not
    academic. An earlier build clustered on a 64-bit dHash and produced
    two headline clusters of 28 and 23 "matching" documents. Both were
    wrong: each held 28 and 23 DISTINCT files under 28 and 23 different
    holder names. The perceptual hash had matched the Aadhaar template
    — same emblem, same bands, same photo box — not the document. A
    fingerprint that flags every Aadhaar card as a duplicate of every
    other Aadhaar card is worse than no fingerprint, because it looks
    like a result. So the visible finding is now exact-file identity,
    which cannot mean anything else.

    SPREAD is what makes a cluster interesting, not size. One image on
    twenty accounts under one name in one station is probably one
    person, or one operator attaching the same file repeatedly. The
    same file behind many DIFFERENT holders across several stations is
    what a mule farm looks like.

    `has_victim` de-prioritises a cluster: a network does not recruit
    the people it defrauds, so a victim-bearing cluster reads as a
    placeholder or default image."""
    fingerprint: str
    #: "exact" = byte-identical file. The only kind served today.
    #: Reserved so a future near-duplicate pass (24x24 dHash, computed
    #: offline — it is O(n^2) and does not belong in a request) can be
    #: added as "similar" without the client having to guess which
    #: kind of match it is looking at.
    match_type: str = "exact"
    #: Signed, time-limited URL for ONE representative image from the
    #: cluster — every member is the same picture, so one is enough.
    #: Lets an officer judge in a glance whether this is a real ID
    #: document or a blank page, which no count can tell them.
    image_url: Optional[str] = None
    images: int = 0
    accounts: int = 0
    distinct_holders: int = 0
    distinct_account_nos: int = 0
    distinct_firs: int = 0
    distinct_ps: int = 0
    distinct_districts: int = 0
    has_victim: bool = False
    account_types: List[str] = []
    members: List[DuplicateIdMember] = []


class DuplicateIdSummary(BaseModel):
    total_hashed: int = 0
    clusters: int = 0
    with_multiple_holders: int = 0
    across_police_stations: int = 0
    across_firs: int = 0
    strong_signal: int = 0
    rows: List[DuplicateIdCluster] = []


class StatementQualityRow(BaseModel):
    """How many source statements ended in each state.

    Shown on the screen rather than hidden in a log, because the honest
    denominator matters: a money trail built from 60% of the statements
    is a different object from one built from all of them, and only this
    row tells the officer which they are looking at."""
    status: str
    files: int = 0


class StatementChannelRow(BaseModel):
    channel: str
    txns: int = 0
    debit: float = 0
    credit: float = 0


class StatementAccountRow(BaseModel):
    """One account's parsed statement totals."""
    account_id: str
    account_holder_name: Optional[str] = None
    account_no: Optional[str] = None
    bank_name: Optional[str] = None
    fir_no: Optional[str] = None
    account_type: Optional[str] = None
    ps_name: Optional[str] = None
    #: Numeric id, carried so the client can hand this row straight to
    #: the FIR trace. FIR numbers are only unique per station, so a
    #: trace needs the id, not the name -- and making the officer pick
    #: the station again from a 45-entry dropdown, when the row already
    #: knows it, is the friction this removes.
    ps_id: Optional[int] = None
    district: Optional[str] = None
    #: all_accounts.branch_state -- the state the BANK BRANCH sits in,
    #: not the police district handling the case. Free text (the
    #: picklist is browser-side only), so it is trimmed server-side and
    #: may be blank on rows predating migrations 010/012.
    branch_state: Optional[str] = None
    txns: int = 0
    debit: float = 0
    credit: float = 0
    first_txn: Optional[date] = None
    last_txn: Optional[date] = None
    #: False when this account contributed rows whose arithmetic was
    #: tested and DISAGREED. Derived per-row, matching the money
    #: columns; it is not the file-level reconciliation flag, which
    #: over-warned on 59% of the accounts it marked.
    verified: bool = True
    #: Rows tested against the balance chain that did NOT agree. These
    #: are excluded from debit/credit above. Unlike untested_txns this
    #: means the source is wrong, not merely uncheckable -- the one
    #: state that earns a warning badge.
    rejected_txns: int = 0
    #: Rows this account contributed that had NOTHING to test against
    #: -- a statement with no balance column cannot be checked, so its
    #: arithmetic is unknown rather than wrong.
    #:
    #: A COUNT, deliberately, and there is no untested_debit sibling.
    #: Summing untested amounts would produce exactly the figure the
    #: chain check exists to withhold: one export whose account number
    #: was read as its debit reached Rs 6.68 QUADRILLION, and no
    #: balance column existed to contradict it. The count says "1,204
    #: rows here are unverifiable" -- true, useful, and impossible to
    #: mistake for money. Their sum would say nothing true at all.
    untested_txns: int = 0


class SharedCounterparty(BaseModel):
    """One destination that received money from MORE THAN ONE account.

    This is the F4 signal in its simplest form. A single mule account
    paying a merchant is ordinary; eleven unrelated mule accounts across
    four FIRs paying the SAME UPI handle is a collection point.

    `key` is an account number or a UPI handle — never a name. Names are
    truncated and misspelt by the banks, and F1 already showed what
    happens when a name is treated as an identity."""
    key: str
    kind: str = "upi"
    counterparty_name: Optional[str] = None
    txns: int = 0
    accounts: int = 0
    firs: int = 0
    total_debit: float = 0


class MoneyTrailSummary(BaseModel):
    """Everything the Money Trail tab renders, in one response.

    The active filters are echoed back so the client labels exports
    from the SERVER's understanding of the request rather than from its
    own state. A PDF that says "Karnataka / Mule" while holding
    something else is worse than one with no label at all."""
    #: Echoed: all | karnataka | other
    state_scope: str = "all"
    #: Echoed: All | Mule | Non-Mule | Victim
    account_type: str = "All"
    #: Accounts with a blank branch_state under the current type filter.
    #: They appear only under "All States" -- see the endpoint for why
    #: they are not swept into "Other States".
    accounts_without_state: int = 0
    transactions: int = 0
    accounts_covered: int = 0
    statements_parsed: int = 0
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    total_debit: float = 0
    total_credit: float = 0
    #: Share of stored rows that came from a reconciled statement.
    verified_pct: float = 0
    #: Rows whose arithmetic could not be tested at all, as a COUNT.
    #: total_debit/total_credit above already exclude them, so without
    #: this number the KPI cards would silently under-report and look
    #: complete. With it the officer reads "Rs X across N txns, plus M
    #: unverifiable" and knows the size of what is missing.
    #:
    #: No rupee figure accompanies it on purpose -- see
    #: StatementAccountRow.untested_txns.
    untested_txns: int = 0
    quality: List[StatementQualityRow] = []
    channels: List[StatementChannelRow] = []
    top_accounts: List[StatementAccountRow] = []
    shared_counterparties: List[SharedCounterparty] = []


class StatementCoverageRow(BaseModel):
    """One account on the Statement Coverage work list.

    Deliberately NOT a financial row — no totals, no transaction count.
    This answers "whose bank statement is still missing, and for how
    long", which is a chasing job, not an analysis.

    `status` is derived, not stored:
        missing     no file attached to the account at all
        unparsed    file attached, the parser has not reached it yet
        unreadable  file attached and read, but yielded no transactions
                    (scanned image needing OCR, or an unknown layout)
        parsed      transactions extracted

    Only `missing` and `unreadable` are anyone's work. `unparsed` is the
    batch job's backlog and clears itself."""
    account_id: str
    account_holder_name: Optional[str] = None
    account_no: Optional[str] = None
    bank_name: Optional[str] = None
    fir_no: Optional[str] = None
    account_type: Optional[str] = None
    ps_name: Optional[str] = None
    district: Optional[str] = None
    branch_state: Optional[str] = None
    status: str = "missing"
    #: Why an `unreadable` file failed, straight from the ledger —
    #: "no text layer (OCR queue)" reads very differently from
    #: "no usable header row" and leads to a different fix.
    detail: Optional[str] = None
    #: FIR registration date, used as the ageing clock. NULL when the
    #: FIR has no case row or its date is outside a believable window.
    fir_date: Optional[date] = None
    #: Days since fir_date. NULL when fir_date is NULL — an unknown age
    #: must not sort as though it were zero.
    days_open: Optional[int] = None


class StatementCoverageSummary(BaseModel):
    """KPI counts plus the filtered work list.

    The counts are over the CURRENT state/type filter but ignore the
    status filter, so the four numbers always add up to total_accounts
    no matter which status is being viewed. A KPI row that changed
    every time you clicked a status would be useless as a denominator."""
    state_scope: str = "all"
    account_type: str = "All"
    status: str = "all"
    total_accounts: int = 0
    missing: int = 0
    unparsed: int = 0
    unreadable: int = 0
    parsed: int = 0
    #: Of `parsed`, how many reconciled. Carried so this tab agrees with
    #: the Money Trail tab rather than implying every parsed statement
    #: is trustworthy.
    parsed_verified: int = 0
    #: Accounts with no branch_state recorded, under the current type
    #: filter. Same reasoning as Money Trail: they sit in neither
    #: Karnataka nor Other States.
    accounts_without_state: int = 0
    rows: List[StatementCoverageRow] = []


class MuleLinkPeer(BaseModel):
    """The account on the other end of a direct transfer.

    `direction` is from the perspective of the row being expanded:
    'out' means this row's account PAID the peer, 'in' means it
    received. Both come from the same stored link, read from opposite
    ends — a transfer is only ever recorded once, on the payer's
    statement."""
    account_id: str
    account_holder_name: Optional[str] = None
    account_no: Optional[str] = None
    bank_name: Optional[str] = None
    fir_no: Optional[str] = None
    ps_name: Optional[str] = None
    direction: str = "out"
    cross_fir: bool = False
    txns: int = 0
    amount: float = 0


class MuleNetworkRow(BaseModel):
    """One mule account and everything it is directly connected to.

    A connection means A's own bank statement records a transfer to B's
    account number, and both A and B are already recorded as Mule. It is
    not inferred from a shared destination and has nothing to do with
    payment gateways — those were deliberately excluded, because every
    account pays BBPS and linking on that would connect everyone to
    everyone.

    `cross_fir` is what makes a row worth reading. Two mules connected
    inside the SAME FIR is expected: they were reported together, which
    is why both are on file. A transfer between mules in DIFFERENT FIRs
    joins two investigations nobody had joined."""
    account_id: str
    account_holder_name: Optional[str] = None
    account_no: Optional[str] = None
    bank_name: Optional[str] = None
    fir_no: Optional[str] = None
    ps_name: Optional[str] = None
    ps_id: Optional[int] = None
    district: Optional[str] = None
    branch_state: Optional[str] = None
    #: Money-trail depth from all_accounts. 1 = the account the victim
    #: paid directly; higher = further from the crime. Nullable, because
    #: it predates migration 012 and older rows never had it.
    layer: Optional[int] = None
    connected: int = 0
    cross_fir: int = 0
    out_links: int = 0
    in_links: int = 0
    txns: int = 0
    amount: float = 0
    #: Embedded rather than fetched on expand. The whole network is
    #: ~1,300 links, so a second round trip per row would cost more
    #: than sending it all once.
    peers: List[MuleLinkPeer] = []



# AccountsFirTrace.network is typed List["MuleNetworkRow"] and this
# file has no `from __future__ import annotations`, so the forward
# reference stays unresolved until the class above exists. Without
# this line FastAPI raises PydanticUndefinedAnnotation the moment it
# builds the response model for /accounts-fir-trace -- at import, so
# the whole app fails to start rather than one route failing.
AccountsFirTrace.model_rebuild()

class MuleNetworkSummary(BaseModel):
    total_links: int = 0
    cross_fir_links: int = 0
    accounts_in_network: int = 0
    #: Mule accounts that have a statement parsed at all — the honest
    #: denominator. An account with no statement cannot show a link, and
    #: its absence from this list says nothing about it.
    accounts_with_statements: int = 0
    rows: List[MuleNetworkRow] = []


class FirCrimeTypeRow(BaseModel):
    """One crime type on the FIR Dashboard's Crime Type tab.

    `prev_count` is the same crime type's count over the immediately
    preceding window of EQUAL length — that comparison is what turns a
    leaderboard into an early-warning panel.

    `cases_with_victim` is the denominator for `amount_lost`, carried
    explicitly because the victim row is 1:1 and optional: legacy cases
    pre-migration-003 have none. Without it a crime type with poor
    victim capture looks low-harm rather than under-recorded."""
    crime_type: str
    count: int = 0
    prev_count: int = 0
    amount_lost: float = 0
    amount_frozen: float = 0
    cases_with_arrest: int = 0
    cases_with_victim: int = 0


class FirCrimeOther(BaseModel):
    """One free-text value operators typed when picking 'Others'.

    Worth surfacing rather than bucketing: a recurring phrase here is
    an emerging modus operandi that the 31-entry classification has not
    caught up with yet."""
    text: str
    count: int = 0


class FirCrimeDistrictCell(BaseModel):
    """One cell of the crime-type x district grid. Only non-zero cells
    are returned; the client fills the rest."""
    crime_type: str
    district: str
    count: int = 0


class FirCrimeTypeReport(BaseModel):
    """Everything the Crime Type tab renders, in one response — six
    panels off one request."""
    types: List[FirCrimeTypeRow] = []
    others: List[FirCrimeOther] = []
    grid: List[FirCrimeDistrictCell] = []
    # Echoed back so the UI can label the comparison window instead of
    # re-deriving it and risking an off-by-one against the server.
    prev_from: date
    prev_to: date


class FirPsCrimeCount(BaseModel):
    """One crime type registered by a given PS in the window. Only
    non-zero entries exist — a GROUP BY cannot produce a zero row, so
    the list is naturally already filtered."""
    crime_type: str
    count: int = 0


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
    # Crime-type split for this PS, biggest first. Populated only for
    # the JSON dashboard route — the PDF/XLSX exports don't render it,
    # so they skip the extra query entirely (2026-08-01).
    crime_types: List[FirPsCrimeCount] = []


# ── NCRP Dashboard (2026-07-30) ─────────────────────────────────
# super_admin-only cross-PS view of everything sitting in
# mule_reports and its six transaction children. mule_reports has
# no ps_id column (pre-dates migration 008) so every per-PS
# aggregation joins through users.ps_id via submitted_by.


class NcrpKpiSummary(BaseModel):
    """Cumulative-to-date KPIs for the NCRP dashboard top row.
    Only submitted reports count; unique_banks is derived from
    money_transfers.bank (the only txn table with a bank column)."""
    total_reports: int = 0
    unique_banks: int = 0
    total_transfer_amount: float = 0
    total_atm_aeps_amount: float = 0


class NcrpPsReportCount(BaseModel):
    """One row per active PS on the NCRP per-PS comparison.
    Zero-filled for silent PSes so the roster stays visible."""
    unit_id: int
    district: str
    ps_id: int
    ps_name: str
    report_count: int = 0


class NcrpBankConcentration(BaseModel):
    """Top-banks bar chart -- money_transfers only. `total_amount`
    is the sum of transaction_amount for rows whose bank matches."""
    bank: str
    transfer_count: int = 0
    total_amount: float = 0


class AccountFirOccurrence(BaseModel):
    """One appearance of an account_no in the All Accounts register.
    Used by the Repeat Accounts drill-down modal to list every FIR
    an account is tied to, plus the layer it sat at in each. Same
    account can appear at different layers across FIRs (Layer 2 in
    FIR X, Layer 4 in FIR Y) -- that's the whole point."""
    fir_no: str
    ps_name: str
    district: str
    layer: Optional[int] = None
    account_type: str
    account_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    branch_state: Optional[str] = None
    created_at: Optional[str] = None    # ISO string, may be null on legacy rows


class RepeatAccount(BaseModel):
    """One aggregated row on the Repeat Accounts view. `account_no`
    identifies the account; `fir_count` is the number of distinct
    FIRs the account has been registered against in the All Accounts
    table across ALL PSes. Repeat >= 2 = candidate serial mule /
    watched account. `sample_firs` gives the operator a quick pivot
    list (truncated to keep responses small)."""
    account_no: str
    bank_name: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_type: str    # Mule or Non-Mule
    branch_state: Optional[str] = None
    fir_count: int = 0
    ps_count: int = 0
    sample_firs: List[str] = []          # up to ~10 distinct FIR Nos
    sample_ps_labels: List[str] = []     # up to ~10 distinct "district / station" labels


class NcrpAtmLocation(BaseModel):
    """Top-ATM chart row -- ATM hotspots ranked by disputed cash
    pulled. Location is a free-text field so the same physical ATM
    may appear under multiple spellings; operators clean by hand."""
    atm_location: str
    withdrawal_count: int = 0
    total_amount: float = 0


class CryptoAccountRow(BaseModel):
    """One account with crypto-linked transactions."""
    account_id: str
    account_holder_name: Optional[str] = None
    account_no: Optional[str] = None
    bank_name: Optional[str] = None
    fir_no: Optional[str] = None
    account_type: Optional[str] = None
    ps_name: Optional[str] = None
    ps_id: Optional[int] = None
    district: Optional[str] = None
    #: Exchanges/assets seen on this account, most frequent first.
    exchanges: List[str] = []
    txns: int = 0
    #: Chain-passed rows only, matching Money Trail. An account whose
    #: crypto rows all failed the balance check shows Rs 0 with its
    #: transaction count intact -- never a confident wrong number.
    debit: float = 0
    credit: float = 0
    first_txn: Optional[date] = None
    last_txn: Optional[date] = None
    #: Rows excluded from the money figures because nothing could test
    #: them. A COUNT, never a sum -- see StatementAccountRow.
    untested_txns: int = 0


class CryptoExchangeRow(BaseModel):
    """Totals per exchange/asset across all accounts."""
    exchange: str
    txns: int = 0
    accounts: int = 0
    debit: float = 0
    credit: float = 0


class CryptoEvidenceRow(BaseModel):
    """One flagged transaction, with the narration that flagged it.

    The narration is the point. This detector has twice produced
    findings that looked right and were not -- 168 "OKX" rows that were
    men called Ashok, 58 "Ethereum" rows that were one bank header
    repeated. An officer must be able to read the evidence rather than
    trust the label, so every row carries the text it matched on.
    """
    exchange: str
    account_holder_name: Optional[str] = None
    account_no: Optional[str] = None
    fir_no: Optional[str] = None
    txn_date: Optional[date] = None
    debit: float = 0
    credit: float = 0
    description: Optional[str] = None
    #: 1 passed / 0 rejected / -1 untested, from the source row.
    chain_ok: int = -1


class CryptoTrailSummary(BaseModel):
    """Everything the Crypto Analysis tab renders."""
    #: Echoed: All | Mule | Non-Mule | Victim
    account_type: str = "All"
    total_txns: int = 0
    accounts: int = 0
    exchanges_seen: int = 0
    total_debit: float = 0
    total_credit: float = 0
    #: Excluded from the money above; reported as a count only.
    untested_txns: int = 0
    #: False when the crypto scan has never been run, so the tab can say
    #: "not yet analysed" rather than "no crypto found" -- those are
    #: very different statements and only one of them is reassuring.
    scanned: bool = False
    by_exchange: List[CryptoExchangeRow] = []
    top_accounts: List[CryptoAccountRow] = []
    evidence: List[CryptoEvidenceRow] = []


class MuleAccountRow(BaseModel):
    """One mule account, connected or not.

    Deliberately NOT the same row as MuleNetworkRow. That one describes
    an account's position in the link graph and only exists if the
    account has a link; this one is the roll of every account recorded
    as Mule, which is the larger and more basic question — "who are
    they" rather than "who is connected to whom"."""
    account_id: str
    fir_no: Optional[str] = None
    ps_name: Optional[str] = None
    district: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_no: Optional[str] = None
    bank_name: Optional[str] = None
    branch_name: Optional[str] = None
    #: Where the BANK BRANCH is, not the police district. The row also
    #: carries `district`, which is the police unit -- they are
    #: different facts and are labelled apart on screen for that reason.
    branch_district: Optional[str] = None
    branch_state: Optional[str] = None
    #: Resolved from the IFSC directory at read time, NOT written back
    #: to the register. Reported beside the entered value rather than
    #: merged with it: 49% of entered branch districts are the
    #: operator's own police district, so merging would bury a real
    #: data-quality problem under a plausible-looking answer.
    branch_district_ifsc: Optional[str] = None
    branch_state_ifsc: Optional[str] = None
    #: Both values present and naming different places, after allowing
    #: for renamings (Bangalore/Bengaluru). A worklist, not an error.
    district_mismatch: bool = False
    ifsc_code: Optional[str] = None
    kyc_mobile: Optional[str] = None
    #: Money-trail depth. 1 = paid directly by the victim.
    layer: Optional[int] = None
    #: Links to other mule accounts. 0 is meaningful and common: most
    #: mule accounts are NOT in the network, either because nobody they
    #: paid is on file or because their statement was never parsed.
    links: int = 0
    cross_fir_links: int = 0
    #: A statement FILE is attached to the account record.
    has_statement_file: bool = False
    #: The statement was parsed and produced transactions. The two
    #: differ for ~18% of the corpus (image-only PDFs), and collapsing
    #: them would report a chasing job as done.
    statement_parsed: bool = False


class MuleAccountList(BaseModel):
    """The All Mule Accounts roll.

    `total_mule_accounts` is counted WITHOUT the limit so the client can
    always tell it received a truncated set and say so on screen. A
    partial list that looks complete is worse than a slow one."""
    #: Echoed back so exports are labelled from what the server applied.
    state_scope: str = "all"
    total_mule_accounts: int = 0
    #: Mule accounts with a blank branch_state. Visible only under
    #: "All States" — they are not swept into "Rest of India", because
    #: an unrecorded state is not evidence of a state outside Karnataka.
    accounts_without_state: int = 0
    in_network: int = 0
    parsed: int = 0
    rows: List[MuleAccountRow] = []
