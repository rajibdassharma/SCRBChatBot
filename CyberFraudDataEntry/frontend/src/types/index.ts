export interface User {
  id: number;
  username: string;
  full_name: string | null;
  role: 'admin' | 'unit_user' | 'super_admin';
  unit_id: number | null;
  unit_name: string | null;
  ps_name: string | null;
}

// ── User Management (PS-admin only) ──
export interface ManagedUser {
  id: number;
  username: string;
  full_name: string | null;
  email: string | null;
  mobile: string | null;
  role: 'admin' | 'unit_user' | 'super_admin';
  is_active: boolean;
  must_change_password: boolean;
  created_at: string | null;
  deactivated_at: string | null;
}

export interface UserCreatePayload {
  full_name: string;
  email: string;
  mobile: string;
}

export interface UserUpdatePayload {
  full_name?: string;
  email?: string;
  mobile?: string;
}

export interface UserCreateResponse {
  user: ManagedUser;
  generated_password: string;
}

export interface PasswordResetResponse {
  user_id: number;
  username: string;
  generated_password: string;
}

export interface UserCount {
  total: number;
  active: number;
}

export interface LoginResponse {
  ok: boolean;
  token: string;
  role: string;
  unit_id: number | null;
  unit_name: string | null;
  ps_id: number | null;
  ps_name: string | null;
  must_change_password: boolean;
}

export interface UnitInfo {
  id: number;
  name: string;
  code: string;
}

// ── Case types ──
// id fields are UUIDv4 strings (VAPT v1.0.1 item 8 rec #2). unit_id and
// submitted_by remain numeric — those reference the still-INT users / units
// tables.

export interface Accomplice {
  id?: string;
  where_met: string;
  where_stayed: string;
  interrogation_details: string;
}

export interface AccusedDetail {
  id?: string;
  photo_path: string;
  email: string;
  mobile: string;
  occupation: string;
  remarks: string;
}

export interface Arrest {
  id?: string;
  name: string;
  address: string;
  email: string;
  aadhar: string;
  pan: string;
  date_of_arrest: string;
  statement: string;
  accomplices: Accomplice[];
  accused_details: AccusedDetail[];
}

export interface Petition {
  id?: string;
  fir_registered: 'yes' | 'no' | 'transferred';
  why_not: string;
  nature: string;
  petition_type: 'amount_lost' | 'fraud_case';
  amount: number;
}

export interface LienAccount {
  id?: string;
  case_type: 'FIR' | 'NCRP' | 'Petition';
  account_no: string;
  amount_lien_marked: number;
  layer: number;
  total_amount_in_account: number;
  bank_name: string;
}

export interface UnfreezeDetail {
  id?: string;
  unfreeze_type: 'letter' | 'court_order';
  crime_no: string;
  bank_name: string;
  account_no: string;
  amount: number;
}

export interface Refund {
  id?: string;
  refunded: 'yes' | 'no';
  victim_name: string;
  amount: number;
  crime_no_or_petition_no: string;
}

export interface Victim {
  id?: string;
  first_name: string;
  last_name: string;
  age: number | null;
  gender: 'Male' | 'Female' | 'Other' | 'Prefer not to say' | '';
  phone: string;
  email: string;
  // Address — structured fields (migration 004). Legacy `address` column
  // still exists in DB but isn't part of the API contract any more.
  house_no: string;
  street_name: string;
  city: string;
  state: string;
  country: string;
  pincode: string;
  amount_lost: number;
  bank_account_no: string;
  bank_name: string;
  bank_branch_address: string;
}

// ── Multi-account rows on the FIR (2026-07-24) ─────────────
// Both surfaces on DSR -> New FIR only. Update Case treats these as
// passthrough (loads them into state, sends unchanged on PUT). The
// backend treats an omitted key as "leave DB rows untouched"; an
// empty array replaces with none.

export interface VictimAccount {
  id?: string;
  bank_name: string;
  branch_name: string;
  branch_address: string;
  state: string;
  district: string;
  ifsc_code: string;
  amount_transferred: number;
}

export interface AccusedAccount {
  id?: string;
  account_holder_name: string;
  bank_name: string;
  branch_name: string;
  branch_address: string;
  state: string;
  district: string;
  ifsc_code: string;
  amount_transferred: number;
}

export interface CaseEntry {
  id?: string;
  unit_id?: number;
  unit_name?: string;
  fir_no: string;
  petition_no?: string;
  registration_date: string;
  case_type: 'NCRP' | 'Walk-In' | 'Petition';
  /** Open-string since migration 016 (2026-07-22) — one of the 31
   *  entries in `CYBER_CRIME_TYPES`, OR a legacy value from the pre-
   *  migration-016 dropdown ({Internet, Digital, Crypto}) that the
   *  frontend surfaces defensively so old cases stay editable. */
  crime_type: string;
  /** Populated only when `crime_type === "Others"`. The operator's
   *  free-text description of the crime, e.g. "Fake job offer via
   *  Facebook Marketplace". Cleared by the backend if crime_type is
   *  anything else. */
  crime_type_other?: string | null;
  /** Free-text list of BNS / BNSS / IT-Act sections, e.g.
   *  "318(4), 319, 340". Nullable — legacy cases pre-migration-015
   *  have no sections. */
  sections?: string | null;
  /** Financial cases include Lien / Unfreeze / Refund tabs and the
   *  victim's bank section. Non-financial cases hide those.
   *  Default true for backwards compatibility with legacy rows. */
  is_financial: boolean;
  facts: string;
  arrests: Arrest[];
  petitions: Petition[];
  lien_accounts: LienAccount[];
  unfreeze_details: UnfreezeDetail[];
  refunds: Refund[];
  // 1:1 — null until the operator fills the Victim Details section.
  victim?: Victim | null;
  // Multi-row account sections captured on DSR -> New FIR. Optional
  // so Update Case can pass them through by simply loading + re-sending
  // (or omit the key entirely to leave the DB rows untouched).
  victim_accounts?: VictimAccount[];
  accused_accounts?: AccusedAccount[];
  submitted_by?: number;
  created_at?: string;
  updated_at?: string;
  status?: 'draft' | 'submitted';
}

export interface CaseListItem {
  id: string;
  unit_id: number;
  unit_name: string | null;
  fir_no: string;
  petition_no?: string;
  registration_date: string;
  case_type: string;
  crime_type: string;
  crime_type_other?: string | null;
  sections?: string | null;
  arrest_count: number;
  created_at: string | null;
  status: string;
}

// -- Mule Report types --

export interface MoneyTransfer {
  id?: string;
  account_no: string;
  transaction_id: string;
  bank: string;
  layer: number;
  dest_account_no: string;
  ifsc_code: string;
  transaction_date: string;
  dest_transaction_id: string;
  transaction_amount: number;
  disputed_amount: number;
  reference_no: string;
  remarks: string;
  action_taken_by_bank: string;
  date_of_action: string;
}

export interface OtherTransaction {
  id?: string;
  account_no: string;
  transaction_id: string;
  transaction_date: string;
  transaction_amount: number;
  reference_no: string;
  remarks: string;
  action_taken_by_bank: string;
  date_of_action: string;
}

export interface TransactionOnHold {
  id?: string;
  account_no: string;
  transaction_id: string;
  hold_date: string;
  hold_amount: number;
  action_taken_by_bank: string;
  date_of_action: string;
  layer: number;
}

export interface OtherLessThan500 {
  id?: string;
  account_no: string;
  transaction_id: string;
  reference_no: string;
  remarks: string;
  action_taken_by_bank: string;
  date_of_action: string;
}

export interface AepsTransaction {
  id?: string;
  account_no: string;
  transaction_id: string;
  withdrawal_date: string;
  withdrawal_amount: number;
  reference_no: string;
  remarks: string;
  action_taken_by_bank: string;
  date_of_action: string;
  layer: number;
}

export interface AtmWithdrawal {
  id?: string;
  account_no: string;
  transaction_id: string;
  withdrawal_datetime: string;
  withdrawal_amount: number;
  disputed_amount: number;
  atm_id: string;
  atm_location: string;
  reference_no: string;
  remarks: string;
  action_taken_by_bank: string;
  date_of_action: string;
}

export interface MuleReport {
  id?: string;
  unit_id?: number;
  unit_name?: string;
  acknowledgement_no: string;
  fir_no: string;
  money_transfers: MoneyTransfer[];
  other_transactions: OtherTransaction[];
  transactions_on_hold: TransactionOnHold[];
  others_less_than_500: OtherLessThan500[];
  aeps_transactions: AepsTransaction[];
  atm_withdrawals: AtmWithdrawal[];
  created_at?: string;
  updated_at?: string;
  status?: 'draft' | 'submitted';
}

export interface MuleReportListItem {
  id: string;
  acknowledgement_no: string;
  fir_no: string;
  unit_name: string | null;
  created_at: string | null;
  money_transfer_count: number;
  other_count: number;
  hold_count: number;
  less_500_count: number;
  aeps_count: number;
  atm_count: number;
  status: string;
}

// -- Dashboard types --

export interface KpiSummary {
  total_cases: number;
  total_arrests: number;
  total_amount_lien_marked: number;
  total_amount_refunded: number;
  total_amount_defreezed: number;
  total_accounts_lien_marked: number;
  total_accounts_defreezed: number;
  units_submitted: number;
  units_total: number;
}

export interface UnitComparison {
  unit_id: number;
  unit_name: string;
  cases: number;
  arrests: number;
  amount_lien_marked: number;
  /** Distinct PSes that have assigned users in this district. Drives whether drill-down is offered. */
  ps_count: number;
}

export interface PsComparison {
  ps_name: string;
  cases: number;
}

export interface TrendPoint {
  report_date: string;
  total_cases: number;
  total_arrests: number;
  total_petitions: number;
}

export interface SubmissionStatus {
  unit_id: number;
  unit_name: string;
  ps_id: number;
  ps_name: string;
  /** Total entries (cases + petitions + mule reports) this PS has made up to the selected date. */
  entry_count: number;
  cases_count: number;
  petitions_count: number;
  mule_count: number;
  /** ISO date of the most recent case or mule report for this PS, or null if never. */
  last_entry_date: string | null;
  /** Whether a DSR row exists for this PS's district on the selected date.
   *  DSR is a district-level concept, so all PS rows in the same district share this flag. */
  dsr_filed: boolean;
  /** Whether this PS explicitly declared "no activity" for the selected date. */
  nil_declared: boolean;
  nil_declared_by_name: string | null;
  /** Cumulative NIL declarations by this PS up to the selected date. */
  nil_count: number;
}

export interface QuietUnit {
  unit_id: number;
  unit_name: string;
  /** null = the unit has never had any entry. */
  days_silent: number | null;
  last_entry_date: string | null;
}

export interface TimeToArrestRow {
  unit_name: string;
  avg_days: number;
  sample_size: number;
}

export interface BankSlaRow {
  bank: string;
  avg_days: number;
  count: number;
}

export interface RecurringAccount {
  account_no: string;
  bank: string | null;
  case_count: number;
  units_count: number;
  total_amount: number;
}

export interface BankConcentration {
  bank: string;
  transaction_count: number;
  total_amount: number;
}

export interface AtmHotspot {
  location: string;
  withdrawal_count: number;
  total_amount: number;
}

export interface LayerBucket {
  layer: number;
  count: number;
}

export interface LienAccountAtLayer {
  lien_id: string;
  account_no: string;
  bank_name: string | null;
  amount_lien_marked: number;
  layer: number;
  case_id: string;
  fir_no: string | null;
  petition_no: string | null;
  registration_date: string | null;
  district: string;
  ps_name: string | null;
}

export interface AccountCaseDetail {
  case_id: string;
  fir_no: string | null;
  petition_no: string | null;
  registration_date: string | null;
  case_type: string | null;
  crime_type: string | null;
  status: string | null;
  district: string;
  ps_name: string | null;
  bank_name: string | null;
  amount: number;
  layer: number | null;
  lien_created_at: string | null;
}

export interface ArrestSummary {
  name: string;
  date_of_arrest: string | null;
  aadhar: string | null;
  pan: string | null;
}

export interface LienSummary {
  account_no: string;
  bank_name: string | null;
  amount_lien_marked: number;
  layer: number | null;
}

export interface PetitionSummary {
  petition_no: string | null;
  nature: string | null;
  petition_type: string | null;
  amount: number;
}

export interface RefundSummary {
  victim_name: string | null;
  amount: number;
  refunded: string | null;
}

export interface CaseDetailFull {
  case_id: string;
  fir_no: string | null;
  petition_no: string | null;
  registration_date: string | null;
  case_type: string | null;
  crime_type: string | null;
  status: string | null;
  facts: string | null;
  district: string;
  ps_name: string | null;
  arrests: ArrestSummary[];
  lien_accounts: LienSummary[];
  petitions: PetitionSummary[];
  refunds: RefundSummary[];
}

export interface DisposalSummary {
  detected: number;
  transferred: number;
  false_cases: number;
  undetected: number;
}

export interface TrialSummary {
  convicted: number;
  discharged: number;
  acquitted: number;
  abated: number;
  compounded: number;
  under_trial: number;
}

export interface PendingByYearRow {
  unit_name: string;
  y2021: number;
  y2022: number;
  y2023: number;
  y2024: number;
  y2025: number;
  y2026: number;
}

// -- DSR + Mule daily entries --

export interface DsrEntry {
  id?: number;
  unit_id?: number;
  unit_name?: string | null;
  report_date: string;
  cases: number;
  petitions: number;
  details_of_arrest: number;
  case_type?: string | null;
  cumulative_amount_lien_marked: number;
  cumulative_accounts_lien_marked: number;
  cumulative_accounts_defreezed: number;
  amount_refunded_to_victim: number;
  ui_cases_pending_2021: number;
  ui_cases_pending_2022: number;
  ui_cases_pending_2023: number;
  ui_cases_pending_2024: number;
  ui_cases_pending_2025: number;
  ui_cases_pending_2026: number;
  disposed_detected_chargesheeted: number;
  disposed_transferred: number;
  disposed_false: number;
  disposed_undetected: number;
  trial_convicted: number;
  trial_discharged: number;
  trial_acquitted: number;
  trial_abated: number;
  trial_compounded: number;
  trial_ut: number;
  submitted_by?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MuleEntry {
  id?: number;
  unit_id?: number;
  unit_name?: string | null;
  report_date: string;
  accounts_most_liens?: string | null;
  recruiters_for_lien_accounts?: string | null;
  accounts_max_money_routed?: string | null;
  accounts_max_transactions?: string | null;
  recency_atm_transactions?: string | null;
  cash_withdrawals_mule_wise?: string | null;
  atm_geo_identification?: string | null;
  atm_table_by_transactions?: string | null;
  cheque_withdrawal_branches?: string | null;
  money_left_system_stats?: string | null;
  crypto_mule_accounts?: string | null;
  submitted_by?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}


// -- Chat (natural-language Q&A over the case DB) --

export interface ChatRequestBody {
  question: string;
}

export interface ChatResponse {
  answer: string;
  sql?: string | null;
  rows: Record<string, unknown>[];
  row_count: number;
  latency_ms: number;
  /** Up to 3 model-suggested follow-up questions. Empty when generation
   *  failed or there were no rows to drill into. */
  followups: string[];
}


// -- NIL Declarations (mark a PS's day as "no activity") --

export interface NilDeclaration {
  id: string;
  unit_id: number;
  ps_id: number;
  declared_by: number;
  declared_by_name: string | null;
  nil_date: string;             // ISO YYYY-MM-DD
  reason: string | null;
  created_at: string | null;
}

export interface NilDeclarationCreatePayload {
  nil_date?: string;            // defaults to today server-side if omitted
  reason?: string;
}


// ── All Accounts (2026-07-18) ────────────────────────────────

export type AccountType = 'Victim' | 'Mule' | 'Non-Mule';

export interface MuleHerder {
  id?: string;
  name: string;
  address: string | null;
  mobile_no: string | null;
}

export interface AllAccount {
  id: string;
  unit_id: number;
  ps_id: number;
  serial_no: number;

  fir_no: string | null;
  ncrp_ack_no: string | null;

  account_no: string;
  bank_name: string;
  branch_name: string | null;
  branch_district: string | null;
  branch_state: string | null;
  layer: number | null;
  ifsc_code: string | null;

  account_holder_name: string;
  kyc_address: string | null;
  kyc_mobile: string | null;
  id_photo_path: string | null;
  account_statement_path: string | null;

  account_type: AccountType;
  mule_herders: MuleHerder[];

  submitted_by: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface AllAccountListItem {
  id: string;
  serial_no: number;
  account_no: string;
  bank_name: string;
  account_holder_name: string;
  account_type: AccountType;
  fir_no: string | null;
  ncrp_ack_no: string | null;
  created_at: string;
}

/** POST/PUT body — the server fills serial_no + ps_id + unit_id. */
export interface AllAccountWritePayload {
  fir_no: string | null;
  ncrp_ack_no: string | null;

  account_no: string;
  bank_name: string;
  branch_name: string | null;
  branch_district: string | null;
  branch_state: string | null;
  layer: number | null;
  ifsc_code: string | null;

  account_holder_name: string;
  kyc_address: string | null;
  kyc_mobile: string | null;
  id_photo_path: string | null;
  account_statement_path: string | null;

  account_type: AccountType;
  mule_herders: MuleHerder[];
}

// ── Accounts dashboard KPIs ─────────────────────────────────

export interface AccountsKpiSummary {
  total_accounts: number;
  victim_accounts: number;
  mule_accounts: number;
  non_mule_accounts: number;
  /** Subset of mule_accounts whose branch_state = 'Karnataka'. Added 2026-07-27. */
  karnataka_mule_accounts: number;
  unique_banks: number;
  unique_mule_herders: number;
  accounts_with_photo: number;
  units_submitted: number;
  units_total: number;
}

export interface AccountsPsComparison {
  unit_id: number;
  unit_name: string;
  ps_id: number;
  ps_name: string;
  total: number;
  /** New accounts created yesterday (relative to the dashboard's
   *  "as of" date). Added 2026-07-24. */
  yesterday_count: number;
  victims: number;
  mules: number;
  non_mules: number;
}

/** Geographic scope for the Account Details map view.
 *  - `state`     : all_accounts.branch_state, all-India
 *  - `district`  : all_accounts.branch_district, Karnataka only
 *  - `reporting` : district of the PS that owns the row. Never blank,
 *                  unlike the branch_* columns, so it stays useful
 *                  while branch coverage is still filling in. */
export type AccountsGeoScope = 'state' | 'district' | 'reporting';

/** One region bucket on the map. `region` is a raw DB value, not an
 *  enum — an empty string means the operator never recorded it, and
 *  anything not in the canonical list renders as "unmapped" rather
 *  than being dropped. */
/** A `type` rather than an `interface` on purpose: TypeScript gives
 *  type aliases an implicit index signature, so this stays assignable
 *  to the map component's generic `GeoRegionDatum`. As an interface it
 *  would not be, and the FIR dashboard could not reuse the same map. */
export type AccountsGeoRegion = {
  region: string;
  total: number;
  victims: number;
  mules: number;
  non_mules: number;
};

/** One point on the FIR Dashboard growth line. `day` is the FIR's
 *  REGISTRATION date, matching the per-PS table on the same page. */
export interface FirDailyPoint {
  day: string;
  /** Total for the day — financial + non_financial. */
  count: number;
  /** Split by cases.is_financial, so the growth chart can draw one line
   *  or two without a second request. */
  financial: number;
  non_financial: number;
}

/** One crime type on the FIR Dashboard's Crime Type tab. */
export interface FirCrimeTypeRow {
  crime_type: string;
  count: number;
  /** Same type over the immediately preceding window of equal length. */
  prev_count: number;
  amount_lost: number;
  amount_frozen: number;
  cases_with_arrest: number;
  /** Denominator for amount_lost — the victim row is 1:1 and optional,
   *  so a low amount can mean low harm OR poor capture. */
  cases_with_victim: number;
}

/** A free-text value typed when "Others" was picked — potentially an
 *  emerging modus operandi the taxonomy hasn't caught up with. */
export interface FirCrimeOther { text: string; count: number }

export interface FirCrimeDistrictCell {
  crime_type: string;
  district: string;
  count: number;
}

/** Whole Crime Type tab in one response. */
export interface FirCrimeTypeReport {
  types: FirCrimeTypeRow[];
  others: FirCrimeOther[];
  grid: FirCrimeDistrictCell[];
  prev_from: string;
  prev_to: string;
}

/** One account inside a duplicate-ID cluster. */
export interface DuplicateIdMember {
  account_id: string;
  account_holder_name: string | null;
  account_no: string | null;
  fir_no: string | null;
  account_type: string | null;
  district: string | null;
  ps_name: string | null;
  bank_name: string | null;
}

/** Accounts whose uploaded ID photo is the same FILE.
 *
 *  `fingerprint` is the SHA-256 of the file bytes — nothing is read out
 *  of the picture. Not a perceptual hash, and deliberately so: an
 *  earlier build clustered on a 64-bit dHash and its two biggest
 *  "findings" turned out to be 28 and 23 completely different documents
 *  that merely shared the Aadhaar layout.
 *
 *  `has_victim` de-prioritises a cluster: a network does not recruit
 *  the people it defrauds, so those read as placeholder images. */
export interface DuplicateIdCluster {
  fingerprint: string;
  /** "exact" = byte-identical file, the only kind served today.
   *  Reserved for a future offline near-duplicate pass ("similar"). */
  match_type: string;
  /** Signed, time-limited URL for one representative image. Every
   *  member is byte-for-byte the same file, so one is enough to judge
   *  whether this is a real ID document or a blank page. */
  image_url: string | null;
  images: number;
  accounts: number;
  distinct_holders: number;
  distinct_account_nos: number;
  distinct_firs: number;
  distinct_ps: number;
  distinct_districts: number;
  has_victim: boolean;
  account_types: string[];
  members: DuplicateIdMember[];
}

/** One state a parsed statement file ended in. Shown on screen rather
 *  than buried in a log: a money trail built from 60% of the statements
 *  is a different object from one built from all of them. */
export interface StatementQualityRow {
  status: string;
  files: number;
}

export interface StatementChannelRow {
  channel: string;
  txns: number;
  debit: number;
  credit: number;
}

/** One account's parsed statement totals. `verified` is false when any
 *  source statement behind it failed its own balance check — the
 *  numbers may be wrong and the UI must say so. */
export interface StatementAccountRow {
  account_id: string;
  account_holder_name: string | null;
  account_no: string | null;
  bank_name: string | null;
  fir_no: string | null;
  account_type: string | null;
  ps_name: string | null;
  /** Numeric station id, carried so a row can be handed straight to the
   *  FIR trace — FIR numbers are only unique per station. */
  ps_id: number | null;
  district: string | null;
  /** State of the BANK BRANCH (all_accounts.branch_state), not the
   *  police district. Free text and ~90% populated. */
  branch_state: string | null;
  txns: number;
  debit: number;
  credit: number;
  first_txn: string | null;
  last_txn: string | null;
  /** False when rows behind this account were tested and DISAGREED.
   *  Row-derived, matching the money columns — not the file-level
   *  reconciliation flag, which over-warned on 59% of what it marked. */
  verified: boolean;
  /** Rows tested against the balance chain that did not agree. These
   *  are excluded from debit/credit. Distinct from untested_txns:
   *  this means wrong, not merely uncheckable. */
  rejected_txns: number;
  /** Rows here that had nothing to check their arithmetic against.
   *  A COUNT — there is no rupee sibling, and that is the point: it
   *  explains a ₹0 row without inventing a total for the part we
   *  cannot vouch for. */
  untested_txns: number;
}

/** A destination paid by MORE THAN ONE account — the collection-point
 *  signal. `key` is an account number or UPI handle, never a name. */
export interface SharedCounterparty {
  key: string;
  kind: string;
  counterparty_name: string | null;
  txns: number;
  accounts: number;
  firs: number;
  total_debit: number;
}

/** One account on the Statement Coverage work list. Identity and age,
 *  not rupees — this is a chasing list, not an analysis. */
export interface StatementCoverageRow {
  account_id: string;
  account_holder_name: string | null;
  account_no: string | null;
  bank_name: string | null;
  fir_no: string | null;
  account_type: string | null;
  ps_name: string | null;
  district: string | null;
  branch_state: string | null;
  /** missing | unparsed | unreadable | parsed — derived, not stored. */
  status: string;
  /** Why an unreadable file failed, from the ledger. */
  detail: string | null;
  fir_date: string | null;
  /** Null when the FIR date is unknown — must not sort as zero. */
  days_open: number | null;
}

export type CoverageStatus = 'all' | 'missing' | 'unparsed' | 'unreadable' | 'parsed';

export interface StatementCoverageSummary {
  state_scope: MoneyTrailScope;
  account_type: string;
  status: CoverageStatus;
  total_accounts: number;
  missing: number;
  unparsed: number;
  unreadable: number;
  parsed: number;
  parsed_verified: number;
  accounts_without_state: number;
  rows: StatementCoverageRow[];
}

/** The account on the other end of a direct mule-to-mule transfer.
 *  `direction` is relative to the row being expanded. */
export interface MuleLinkPeer {
  account_id: string;
  account_holder_name: string | null;
  account_no: string | null;
  bank_name: string | null;
  fir_no: string | null;
  ps_name: string | null;
  direction: string;
  cross_fir: boolean;
  txns: number;
  amount: number;
}

/** A mule account and the other mule accounts it transfers with.
 *  Not shared-destination, not payment gateways — A's statement names
 *  B's account number and both are recorded as Mule. */
export interface MuleNetworkRow {
  account_id: string;
  account_holder_name: string | null;
  account_no: string | null;
  bank_name: string | null;
  fir_no: string | null;
  ps_name: string | null;
  ps_id: number | null;
  district: string | null;
  branch_state: string | null;
  /** Money-trail depth. 1 = paid directly by the victim; higher = further
   *  from the crime. Null on rows predating migration 012. */
  layer: number | null;
  connected: number;
  cross_fir: number;
  out_links: number;
  in_links: number;
  txns: number;
  amount: number;
  peers: MuleLinkPeer[];
}

/** One account recorded as Mule, connected or not.
 *
 *  Deliberately not MuleNetworkRow. That describes an account's place
 *  in the link graph and only exists if the account HAS a link; this is
 *  the roll of every mule account, which is the larger set. */
export interface MuleAccountRow {
  account_id: string;
  fir_no: string | null;
  ps_name: string | null;
  district: string | null;
  account_holder_name: string | null;
  account_no: string | null;
  bank_name: string | null;
  branch_name: string | null;
  branch_state: string | null;
  ifsc_code: string | null;
  kyc_mobile: string | null;
  layer: number | null;
  /** 0 is meaningful and common: most mule accounts are not in the
   *  network because nothing they paid is on file yet. */
  links: number;
  cross_fir_links: number;
  /** A file is attached. NOT the same as parsed — ~18% of the corpus is
   *  image-only PDFs that satisfy this and yield no transactions. */
  has_statement_file: boolean;
  statement_parsed: boolean;
}

export interface MuleAccountList {
  state_scope: string;
  /** Counted without the row limit, so the client can tell it was
   *  truncated and say so. */
  total_mule_accounts: number;
  accounts_without_state: number;
  in_network: number;
  parsed: number;
  rows: MuleAccountRow[];
}

export interface MuleNetworkSummary {
  total_links: number;
  cross_fir_links: number;
  accounts_in_network: number;
  accounts_with_statements: number;
  rows: MuleNetworkRow[];
}

/** Filter for the branch state of the account, not the police district. */
export type MoneyTrailScope = 'all' | 'karnataka' | 'other';

export interface MoneyTrailSummary {
  /** Echoed by the server so exports are labelled from what the server
   *  actually applied, not from client state that may have moved on. */
  state_scope: MoneyTrailScope;
  account_type: string;
  /** Accounts with no branch state recorded. They appear only under
   *  "All States" — see the endpoint for why they are not swept into
   *  "Other States". */
  accounts_without_state: number;
  transactions: number;
  accounts_covered: number;
  statements_parsed: number;
  date_from: string | null;
  date_to: string | null;
  /** Summed over RECONCILED statements only — see the endpoint docstring. */
  total_debit: number;
  total_credit: number;
  verified_pct: number;
  /** Transactions excluded from total_debit/total_credit because
   *  nothing could test them. Shown so the KPI cards do not read as
   *  complete when they are not. */
  untested_txns: number;
  quality: StatementQualityRow[];
  channels: StatementChannelRow[];
  top_accounts: StatementAccountRow[];
  shared_counterparties: SharedCounterparty[];
}

export interface DuplicateIdSummary {
  total_hashed: number;
  clusters: number;
  with_multiple_holders: number;
  across_police_stations: number;
  across_firs: number;
  strong_signal: number;
  rows: DuplicateIdCluster[];
}

export interface AccountsBankConcentration {
  bank_name: string;
  total: number;
  victims: number;
  mules: number;
  non_mules: number;
}

/** One point on the Account Details daily-growth line chart. */
export interface AccountsDailyPoint {
  day: string;
  count: number;
}

/** One `{layer, count}` point on the layer-histogram bar chart. */
export interface LayerCountPoint {
  layer: number;
  count: number;
}

// ── Accounts Dashboard → Deep Analysis → FIR Trace ─────────────

export interface FirTraceCase {
  case_id: string | null;
  fir_no: string;
  unit_name: string | null;
  ps_name: string | null;
  registration_date: string | null;
  case_type: string | null;
  crime_type: string | null;
  victim_name: string | null;
  amount_lost: number;
}

/** One account touching an FIR, from any of the 5 source tables.
 *  `source` tags where it came from so the operator can trace the
 *  row back to its owning entry point. */
export type FirTraceSource =
  | 'all_accounts'
  | 'lien_accounts'
  | 'victim_accounts'
  | 'accused_accounts'
  | 'money_transfer';

export interface FirTraceAccount {
  source: FirTraceSource;
  layer: number | null;
  account_no: string | null;
  account_holder_name: string | null;
  bank_name: string | null;
  branch_name: string | null;
  branch_state: string | null;
  ifsc_code: string | null;
  amount: number;
  account_type: string | null;
  /** Only for rows from all_accounts — the four case-child tables carry
   *  no id to join on, so everything below is 0 for them. That is a gap
   *  in the source, not a statement that the account is clean. */
  account_id: string | null;
  crypto_txns: number;
  crypto_exchanges: string[];
  crypto_debit: number;
  /** Links to mule accounts OUTSIDE this FIR. Counted, not drawn — each
   *  is a thread leading out of this case file. */
  external_links: number;
}

/** One statement-derived transfer between two accounts in the trace.
 *
 *  The first edge on the Graphical Analysis view that is EVIDENCE
 *  rather than layout: layer columns say how far from the victim an
 *  account sits, never who paid whom. An arrow means one account's own
 *  bank statement names the other's account number. */
export interface FirTraceFlow {
  src_account_id: string;
  dst_account_id: string;
  txns: number;
  amount: number;
  cross_fir: boolean;
}

export interface AccountsFirTrace {
  fir_no: string;
  case: FirTraceCase | null;
  accounts: FirTraceAccount[];
  /** Transfers where BOTH ends are in `accounts`. Empty for most FIRs:
   *  only 177 of 3,822 have an internal link, because a link needs both
   *  accounts' statements parsed AND both recorded as Mule. */
  flows: FirTraceFlow[];
  warnings: string[];
}

/** Layer 1..15 distribution of all_accounts, split by branch state.
 *  KA = branch_state = 'Karnataka'. Rest = every other value INCLUDING
 *  NULL. Accounts with a NULL layer are counted separately so the UI
 *  can surface them in a chart subtitle. */
export interface AccountsLayerDistribution {
  ka: LayerCountPoint[];
  rest: LayerCountPoint[];
  unknown_layer_ka: number;
  unknown_layer_rest: number;
}

// ── Portals DSR ────────────────────────────────────────────

export type PortalsDsrStatus = 'draft' | 'submitted';

/** Every metric column on the portals_dsr_entries table.
 *  Keep in sync with schemas.portals_dsr on the backend. */
export interface PortalsDsrMetrics {
  // NCRP (3)
  ncrp_received: number;
  ncrp_disposed: number;
  ncrp_pending: number;

  // Samanvaya (6)
  samanvaya_request_received: number;
  samanvaya_actions: number;
  samanvaya_action_pending: number;
  samanvaya_request_sent: number;
  samanvaya_reply_received: number;
  samanvaya_replies_pending: number;

  // Sahayog (3)
  sahayog_unlawful_content_removal: number;
  sahayog_intermediary_requests: number;
  sahayog_crypto_requests: number;

  // GRM (3)
  grm_request_received: number;
  grm_action: number;
  grm_pending: number;

  // MRM (3)
  mrm_request_received: number;
  mrm_action: number;
  mrm_pending: number;

  // Bharatpol (1)
  bharatpol_request_received: number;

  // OCWC (3)
  ocwc_received: number;
  ocwc_disposed: number;
  ocwc_pending: number;

  // NCMEC Tipline (3)
  ncmec_received: number;
  ncmec_disposed: number;
  ncmec_pending: number;
}

export interface PortalsDsrWritePayload extends PortalsDsrMetrics {
  report_date: string;   // YYYY-MM-DD
  status: PortalsDsrStatus;
}

export interface PortalsDsrEntry extends PortalsDsrWritePayload {
  id: string;
  unit_id: number;
  ps_id: number;
  submitted_by: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface PortalsDsrListItem {
  id: string;
  report_date: string;
  status: PortalsDsrStatus;
  total: number;
  submitted_by: number | null;
  created_at: string;
}

export interface PortalsDsrKpiSummary extends PortalsDsrMetrics {
  total_entries: number;
  units_submitted: number;
  units_total: number;
}

export interface PortalsDsrPsComparison extends PortalsDsrMetrics {
  unit_id: number;
  unit_name: string;
  ps_id: number;
  ps_name: string;
  /** Number of shift-batch submissions on the target date. */
  entries: number;
  /** Grand total across all 25 metric columns (pending as LATEST,
   *  others as SUM within the day). Coarse ranking metric only. */
  total: number;
}

// -- Daily Work Done (Investigation Log) --
// Mirrors backend/schemas/daily_work.py. One row per (PS, FIR, date).

export type DailyWorkFinalReport = 'A' | 'B' | 'C';

export interface DailyWorkWritePayload {
  report_date: string;
  fir_no: string;
  // Red — Notices
  notices_35_41a_count: number;
  notices_91_92_94_banks: number;
  notices_91_92_94_intermediary: number;
  notices_91_92_94_account_holder: number;
  notices_91_92_94_cdr_ipdr: number;
  // Yellow — Lien / Unlien
  lien_requests_count: number;
  freeze_requests_count: number;
  total_lien_amount: number;
  unlien_requests_count: number;
  defreeze_requests_count: number;
  total_unlien_amount: number;
  // Green — Outcomes
  arrests_count: number;
  statements_count: number;
  final_report: DailyWorkFinalReport | null;
}

export interface DailyWorkEntry extends DailyWorkWritePayload {
  id: number;
  unit_id: number;
  ps_id: number;
  unit_name?: string | null;
  submitted_by?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

// Dashboard aggregation shape — mirrors backend/api/routes_daily_work.py
// `daily_work_dashboard` response.

export interface DailyWorkDashboardTotals {
  entries: number;
  unique_firs: number;
  notices_35_41a: number;
  notices_91_92_94_total: number;
  notices_91_92_94_banks: number;
  notices_91_92_94_intermediary: number;
  notices_91_92_94_account_holder: number;
  notices_91_92_94_cdr_ipdr: number;
  lien_requests_total: number;
  freeze_requests_total: number;
  total_lien_amount: number;
  unlien_requests_total: number;
  defreeze_requests_total: number;
  total_unlien_amount: number;
  arrests: number;
  statements: number;
}

export interface DailyWorkFinalReportSplit {
  a: number;
  b: number;
  c: number;
  open: number;
}

export interface DailyWorkDailyPoint {
  day: string;
  notices: number;
  arrests: number;
  statements: number;
}

/** One police station's investigation activity. super_admin only —
 *  a PS-level admin gets a single row, so the list stays empty. */
export interface DailyWorkPsRow {
  unit_id: number;
  district: string;
  ps_id: number;
  ps_name: string;
  entries: number;
  unique_firs: number;
  notices: number;
  lien_requests: number;
  arrests: number;
  statements: number;
  total_lien_amount: number;
}

export interface DailyWorkDashboard {
  date_from: string;
  date_to: string;
  totals: DailyWorkDashboardTotals;
  final_report_split: DailyWorkFinalReportSplit;
  daily: DailyWorkDailyPoint[];
  /** Cross-PS comparison; empty for a PS-level admin. */
  per_ps?: DailyWorkPsRow[];
  /** True when the response spans every station rather than just the
   *  caller's — lets the page label itself instead of guessing. */
  cross_ps?: boolean;
}

// -- FIR Dashboard (DSR module) — per-PS performance table --
// Mirrors backend/schemas/dashboard.py FirPsPerformanceRow.

// ── Daily report preview shapes (2026-07-24) ────────────────
// Returned by /api/v1/reports/portals-dsr-daily.json and
// daily-work-daily.json — same aggregation as the corresponding
// PDF/XLSX renderers. All 45 active PSes are always returned; a
// PS that didn't submit gets null for every metric so the UI
// renders a blank cell (not "0").

export interface PortalsDsrDailyPreviewRow {
  ps_id: number;
  ps_name: string;
  district: string;
  ncrp_received: number | null;
  ncrp_disposed: number | null;
  ncrp_pending: number | null;
  samanvaya_request_received: number | null;
  samanvaya_actions: number | null;
  samanvaya_action_pending: number | null;
  samanvaya_request_sent: number | null;
  samanvaya_reply_received: number | null;
  samanvaya_replies_pending: number | null;
  sahayog_unlawful_content_removal: number | null;
  sahayog_intermediary_requests: number | null;
  sahayog_crypto_requests: number | null;
  grm_request_received: number | null;
  grm_action: number | null;
  grm_pending: number | null;
  mrm_request_received: number | null;
  mrm_action: number | null;
  mrm_pending: number | null;
  bharatpol_request_received: number | null;
  ocwc_received: number | null;
  ocwc_disposed: number | null;
  ocwc_pending: number | null;
  ncmec_received: number | null;
  ncmec_disposed: number | null;
  ncmec_pending: number | null;
}

export interface DailyWorkDailyPreviewRow {
  ps_id: number;
  ps_name: string;
  district: string;
  fir_count: number;
  notices_35_41a_count: number | null;
  notices_91_92_94_banks: number | null;
  notices_91_92_94_intermediary: number | null;
  notices_91_92_94_account_holder: number | null;
  notices_91_92_94_cdr_ipdr: number | null;
  lien_requests_count: number | null;
  freeze_requests_count: number | null;
  total_lien_amount: number | null;
  unlien_requests_count: number | null;
  defreeze_requests_count: number | null;
  total_unlien_amount: number | null;
  arrests_count: number | null;
  statements_count: number | null;
  final_report_a: number;
  final_report_b: number;
  final_report_c: number;
  final_report_abc: string | null;
}

/** One crime type registered by a PS in the window. Only non-zero
 *  entries are sent — a GROUP BY cannot emit a zero row. */
export interface FirPsCrimeCount { crime_type: string; count: number }

export interface FirPsPerformanceRow {
  unit_id: number;
  district: string;
  ps_id: number;
  ps_name: string;
  fir_count: number;
  /** FIRs registered yesterday (server today - 1), independent of the
   *  from/to window. Added 2026-07-25. */
  yesterday_count: number;
  /** Crime-type split for this PS, biggest first. Non-zero only.
   *  Populated by the dashboard route; absent from the exports. */
  crime_types?: FirPsCrimeCount[];
}

/* ── NCRP Dashboard (2026-07-30, super_admin only) ─────────────── */

export interface NcrpKpiSummary {
  total_reports: number;
  unique_banks: number;
  total_transfer_amount: number;
  total_atm_aeps_amount: number;
}

export interface NcrpPsReportCount {
  unit_id: number;
  district: string;
  ps_id: number;
  ps_name: string;
  report_count: number;
}

export interface NcrpBankConcentration {
  bank: string;
  transfer_count: number;
  total_amount: number;
}

export interface NcrpAtmLocation {
  atm_location: string;
  withdrawal_count: number;
  total_amount: number;
}

/** One row per All Accounts occurrence of an account_no. Drives
 *  the Repeat Accounts drill-down modal. */
export interface AccountFirOccurrence {
  fir_no: string;
  ps_name: string;
  district: string;
  layer: number | null;
  account_type: string;
  account_holder_name: string | null;
  bank_name: string | null;
  branch_state: string | null;
  created_at: string | null;
}

/** Repeat Accounts (super_admin) -- one row per account_no seen in
 *  >= min_firs distinct FIRs across all PSes. */
export interface RepeatAccount {
  account_no: string;
  bank_name: string | null;
  account_holder_name: string | null;
  account_type: string;    // 'Mule' or 'Non-Mule'
  branch_state: string | null;
  fir_count: number;
  ps_count: number;
  sample_firs: string[];
  sample_ps_labels: string[];
}

/** One account with crypto-linked transactions. */
export interface CryptoAccountRow {
  account_id: string;
  account_holder_name: string | null;
  account_no: string | null;
  bank_name: string | null;
  fir_no: string | null;
  account_type: string | null;
  ps_name: string | null;
  ps_id: number | null;
  district: string | null;
  /** Exchanges/assets seen on this account. */
  exchanges: string[];
  txns: number;
  /** Chain-passed rows only — same rule as Money Trail. */
  debit: number;
  credit: number;
  first_txn: string | null;
  last_txn: string | null;
  /** Excluded from the money figures. A count, never a sum. */
  untested_txns: number;
}

export interface CryptoExchangeRow {
  exchange: string;
  txns: number;
  accounts: number;
  debit: number;
  credit: number;
}

/** One flagged transaction WITH the narration that flagged it — the
 *  evidence an officer needs to reject a false positive in seconds. */
export interface CryptoEvidenceRow {
  exchange: string;
  account_holder_name: string | null;
  account_no: string | null;
  fir_no: string | null;
  txn_date: string | null;
  debit: number;
  credit: number;
  description: string | null;
  /** 1 passed / 0 rejected / -1 untested. */
  chain_ok: number;
}

export interface CryptoTrailSummary {
  account_type: string;
  total_txns: number;
  accounts: number;
  exchanges_seen: number;
  total_debit: number;
  total_credit: number;
  untested_txns: number;
  /** False when the scan has never run. "Not yet analysed" and "no
   *  crypto found" are different answers and only one is reassuring. */
  scanned: boolean;
  by_exchange: CryptoExchangeRow[];
  top_accounts: CryptoAccountRow[];
  evidence: CryptoEvidenceRow[];
}
