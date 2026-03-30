export interface User {
  id: number;
  username: string;
  full_name: string | null;
  role: 'admin' | 'unit_user';
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
}

export interface UnitInfo {
  id: number;
  name: string;
  code: string;
}

// ── Case types ──

export interface Accomplice {
  id?: number;
  where_met: string;
  where_stayed: string;
  interrogation_details: string;
}

export interface AccusedDetail {
  id?: number;
  photo_path: string;
  email: string;
  mobile: string;
  occupation: string;
  remarks: string;
}

export interface Arrest {
  id?: number;
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
  id?: number;
  fir_registered: 'yes' | 'no' | 'transferred';
  why_not: string;
  nature: string;
  petition_type: 'amount_lost' | 'fraud_case';
  amount: number;
}

export interface LienAccount {
  id?: number;
  case_type: 'FIR' | 'NCRP' | 'Petition';
  account_no: string;
  amount_lien_marked: number;
  layer: number;
  total_amount_in_account: number;
  bank_name: string;
}

export interface UnfreezeDetail {
  id?: number;
  unfreeze_type: 'letter' | 'court_order';
  crime_no: string;
  bank_name: string;
  account_no: string;
  amount: number;
}

export interface Refund {
  id?: number;
  refunded: 'yes' | 'no';
  victim_name: string;
  amount: number;
  crime_no_or_petition_no: string;
}

export interface CaseEntry {
  id?: number;
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
  id: number;
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
  id?: number;
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
  id?: number;
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
  id?: number;
  account_no: string;
  transaction_id: string;
  hold_date: string;
  hold_amount: number;
  action_taken_by_bank: string;
  date_of_action: string;
  layer: number;
}

export interface OtherLessThan500 {
  id?: number;
  account_no: string;
  transaction_id: string;
  reference_no: string;
  remarks: string;
  action_taken_by_bank: string;
  date_of_action: string;
}

export interface AepsTransaction {
  id?: number;
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
  id?: number;
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
  id?: number;
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
  id: number;
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
  units_submitted: number;
  units_total: number;
}

export interface UnitComparison {
  unit_name: string;
  cases: number;
  arrests: number;
  amount_lien_marked: number;
}
