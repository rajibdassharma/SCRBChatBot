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

export interface PortalsDsrPsComparison {
  unit_id: number;
  unit_name: string;
  ps_id: number;
  ps_name: string;
  entries: number;
  total: number;
  /** Submitted rows whose report_date is yesterday (server today - 1),
   *  independent of the from/to window. Added 2026-07-25. */
  yesterday_count: number;
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

export interface DailyWorkDashboard {
  date_from: string;
  date_to: string;
  totals: DailyWorkDashboardTotals;
  final_report_split: DailyWorkFinalReportSplit;
  daily: DailyWorkDailyPoint[];
}

// -- FIR Dashboard (DSR module) — per-PS performance table --
// Mirrors backend/schemas/dashboard.py FirPsPerformanceRow.

export interface FirPsPerformanceRow {
  unit_id: number;
  district: string;
  ps_id: number;
  ps_name: string;
  fir_count: number;
  /** FIRs registered yesterday (server today - 1), independent of the
   *  from/to window. Added 2026-07-25. */
  yesterday_count: number;
}
