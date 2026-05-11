export interface User {
  id: number;
  username: string;
  full_name: string | null;
  role: 'admin' | 'unit_user' | 'super_admin';
  unit_id: number | null;
  unit_name: string | null;
  ps_name: string | null;
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

export interface CaseEntry {
  id?: string;
  unit_id?: number;
  unit_name?: string;
  fir_no: string;
  petition_no?: string;
  registration_date: string;
  case_type: 'NCRP' | 'Walk-In' | 'Petition';
  crime_type: 'Internet' | 'Digital' | 'Crypto';
  facts: string;
  arrests: Arrest[];
  petitions: Petition[];
  lien_accounts: LienAccount[];
  unfreeze_details: UnfreezeDetail[];
  refunds: Refund[];
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
  total_accounts_lien_marked: number;
  total_accounts_defreezed: number;
  units_submitted: number;
  units_total: number;
}

export interface UnitComparison {
  unit_name: string;
  cases: number;
  arrests: number;
  amount_lien_marked: number;
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
  dsr_submitted: boolean;
  mule_submitted: boolean;
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
