import { apiFetch } from './client';

export type FirFinancialFilter = 'all' | 'yes' | 'no';
import type {
  KpiSummary, UnitComparison, PsComparison, SubmissionStatus, TrendPoint,
  QuietUnit, TimeToArrestRow, BankSlaRow,
  RecurringAccount, BankConcentration, AtmHotspot, LayerBucket, LienAccountAtLayer,
  AccountCaseDetail, CaseDetailFull,
  DisposalSummary, TrialSummary, PendingByYearRow,
  AccountsKpiSummary, AccountsPsComparison, AccountsBankConcentration,
  AccountsGeoRegion, AccountsGeoScope, DuplicateIdSummary,
  AllAccount,
  PortalsDsrKpiSummary, PortalsDsrPsComparison,
  FirPsPerformanceRow, FirDailyPoint, FirCrimeTypeReport,
  AccountsDailyPoint, AccountsLayerDistribution,
  AccountsFirTrace,
  NcrpKpiSummary, NcrpPsReportCount, NcrpBankConcentration, NcrpAtmLocation,
  RepeatAccount, AccountFirOccurrence,
  MoneyTrailSummary, MoneyTrailScope,
  StatementCoverageSummary, CoverageStatus, MuleNetworkSummary,
  CryptoTrailSummary,
  MuleAccountList,
} from '../../types';

/** All Accounts dashboard — KPI cards + per-PS comparison. */
export async function getAccountsSummary(date: string): Promise<AccountsKpiSummary> {
  return apiFetch<AccountsKpiSummary>(`/api/v1/dashboard/accounts-summary?date=${date}`);
}

export async function getAccountsComparison(date: string): Promise<AccountsPsComparison[]> {
  return apiFetch<AccountsPsComparison[]>(`/api/v1/dashboard/accounts-comparison?date=${date}`);
}

/** Per-day FIR counts for the FIR Dashboard growth line. Same window
 *  and same filters as the per-PS table, so the series sums to the
 *  table's grand total. */
export async function getFirDailyGrowth(
  from: string, to: string,
): Promise<FirDailyPoint[]> {
  const qs = new URLSearchParams({ from, to });
  return apiFetch<FirDailyPoint[]>(`/api/v1/dashboard/fir-daily-growth?${qs.toString()}`);
}

/** Crime Type tab — six panels off one request. */
export async function getFirCrimeTypes(
  from: string, to: string, financial: FirFinancialFilter = 'all',
): Promise<FirCrimeTypeReport> {
  const qs = new URLSearchParams({ from, to });
  if (financial !== 'all') qs.set('financial', financial);
  return apiFetch<FirCrimeTypeReport>(`/api/v1/dashboard/fir-crime-types?${qs.toString()}`);
}

/** Region rollup for the Account Details map view. Returns only regions
 *  with at least one account — the caller fills the zeros from the
 *  canonical state / district lists. */
export async function getAccountsByGeography(
  date: string,
  scope: AccountsGeoScope = 'state',
  // Defaults to 'All' because the map shades from a client-side metric
  // toggle — one fetch serves the Mule / Victim / Non-Mule / All views
  // and keeps the full breakdown available in every tooltip.
  accountType: 'Victim' | 'Mule' | 'Non-Mule' | 'All' = 'All',
): Promise<AccountsGeoRegion[]> {
  const qs = new URLSearchParams({ date, scope, account_type: accountType });
  return apiFetch<AccountsGeoRegion[]>(`/api/v1/dashboard/accounts-geo?${qs.toString()}`);
}

/** F1 — accounts sharing the same ID photo. super_admin only; the
 *  server returns 403 for anyone else. */
/** Direct mule-to-mule transfer network (F4). super_admin only. */
export async function getMuleNetwork(
  crossFirOnly = true, stateScope: MoneyTrailScope = 'all', limit = 20000,
): Promise<MuleNetworkSummary> {
  const qs = new URLSearchParams({
    cross_fir_only: String(crossFirOnly),
    state_scope: stateScope,
    limit: String(limit),
  });
  return apiFetch<MuleNetworkSummary>(`/api/v1/dashboard/mule-network?${qs.toString()}`);
}

/** Every account recorded as Mule, connected or not (F4).
 *  super_admin only. Not a page of results — the client paginates and
 *  exports the whole set, so one round trip carries all of it. */
export async function getMuleAccounts(
  stateScope: MoneyTrailScope = 'all', limit = 30000,
): Promise<MuleAccountList> {
  const qs = new URLSearchParams({
    state_scope: stateScope,
    limit: String(limit),
  });
  return apiFetch<MuleAccountList>(`/api/v1/dashboard/mule-accounts?${qs.toString()}`);
}

/** Statement coverage work list (F2). super_admin only; 403 otherwise. */
export async function getStatementCoverage(
  stateScope: MoneyTrailScope = 'all', accountType = 'All',
  status: CoverageStatus = 'missing', limit = 25000,
): Promise<StatementCoverageSummary> {
  const qs = new URLSearchParams({
    state_scope: stateScope, account_type: accountType,
    status, limit: String(limit),
  });
  return apiFetch<StatementCoverageSummary>(
    `/api/v1/dashboard/statement-coverage?${qs.toString()}`);
}

/** Parsed bank-statement rollup (F2). super_admin only; 403 otherwise. */
export async function getMoneyTrail(
  stateScope: MoneyTrailScope = 'all', accountType = 'All',
  accountLimit = 20000,
): Promise<MoneyTrailSummary> {
  const qs = new URLSearchParams({
    state_scope: stateScope,
    account_type: accountType,
    account_limit: String(accountLimit),
  });
  return apiFetch<MoneyTrailSummary>(`/api/v1/dashboard/money-trail?${qs.toString()}`);
}

export async function getDuplicateIds(
  minAccounts = 2, limit = 2000,
): Promise<DuplicateIdSummary> {
  const qs = new URLSearchParams({
    min_accounts: String(minAccounts), limit: String(limit),
  });
  return apiFetch<DuplicateIdSummary>(`/api/v1/dashboard/duplicate-ids?${qs.toString()}`);
}

/** Top N banks by account-count for the Dashboard Overview insight panel. */
export async function getAccountsTopBanks(
  date: string, limit = 10,
): Promise<AccountsBankConcentration[]> {
  return apiFetch<AccountsBankConcentration[]>(
    `/api/v1/dashboard/accounts-top-banks?date=${date}&limit=${limit}`,
  );
}

/** Portals DSR — grand totals for a SINGLE DSR date. Non-pending
 *  metrics summed across the day's shift-batches; pending metrics
 *  take the LATEST value per PS. Only submitted entries counted. */
export async function getPortalsSummary(date: string): Promise<PortalsDsrKpiSummary> {
  return apiFetch<PortalsDsrKpiSummary>(
    `/api/v1/dashboard/portals-summary?date=${encodeURIComponent(date)}`,
  );
}

/** Portals DSR — one row per ACTIVE PS on the selected date, every
 *  metric column populated. Silent PSes come back as zeros so the
 *  UI can show who has and hasn't reported. */
export async function getPortalsComparison(date: string): Promise<PortalsDsrPsComparison[]> {
  return apiFetch<PortalsDsrPsComparison[]>(
    `/api/v1/dashboard/portals-comparison?date=${encodeURIComponent(date)}`,
  );
}

/** Drill-down: full account-detail rows (with mule herders eager-loaded)
 *  for the requested (unit_id, ps_id) up to the given cutoff date. */
export async function getAccountsDetailsByPs(
  date: string, unitId: number, psId: number,
): Promise<AllAccount[]> {
  return apiFetch<AllAccount[]>(
    `/api/v1/dashboard/accounts-details-by-ps?date=${date}&unit_id=${unitId}&ps_id=${psId}`,
  );
}

export async function getSummary(date: string): Promise<KpiSummary> {
  return apiFetch<KpiSummary>(`/api/v1/dashboard/summary?date=${date}`);
}

export async function getUnitComparison(date: string): Promise<UnitComparison[]> {
  return apiFetch<UnitComparison[]>(`/api/v1/dashboard/unit-comparison?date=${date}`);
}

export async function getCasesByPs(date: string, unitId: number): Promise<PsComparison[]> {
  return apiFetch<PsComparison[]>(`/api/v1/dashboard/cases-by-ps?date=${date}&unit_id=${unitId}`);
}

export async function getTrends(from: string, to: string): Promise<TrendPoint[]> {
  return apiFetch<TrendPoint[]>(`/api/v1/dashboard/trends?from=${from}&to=${to}`);
}

export async function getSubmissionStatus(date: string): Promise<SubmissionStatus[]> {
  return apiFetch<SubmissionStatus[]>(`/api/v1/dashboard/submission-status?date=${date}`);
}

export async function getQuietUnits(date: string, thresholdDays = 7): Promise<QuietUnit[]> {
  return apiFetch<QuietUnit[]>(`/api/v1/dashboard/quiet-units?date=${date}&threshold_days=${thresholdDays}`);
}

export async function getTimeToArrest(date: string, lookbackDays = 90): Promise<TimeToArrestRow[]> {
  return apiFetch<TimeToArrestRow[]>(`/api/v1/dashboard/time-to-arrest?date=${date}&lookback_days=${lookbackDays}`);
}

export async function getBankActionSla(date: string, lookbackDays = 180): Promise<BankSlaRow[]> {
  return apiFetch<BankSlaRow[]>(`/api/v1/dashboard/bank-action-sla?date=${date}&lookback_days=${lookbackDays}`);
}

export async function getRecurringAccounts(date: string, minCases = 2, limit = 2000): Promise<RecurringAccount[]> {
  return apiFetch<RecurringAccount[]>(`/api/v1/dashboard/recurring-mule-accounts?date=${date}&min_cases=${minCases}&limit=${limit}`);
}

export async function getAccountCases(date: string, accountNo: string): Promise<AccountCaseDetail[]> {
  return apiFetch<AccountCaseDetail[]>(`/api/v1/dashboard/account-cases?date=${date}&account_no=${encodeURIComponent(accountNo)}`);
}

export async function getCaseDetail(caseId: string): Promise<CaseDetailFull> {
  return apiFetch<CaseDetailFull>(`/api/v1/dashboard/case-detail?case_id=${encodeURIComponent(caseId)}`);
}

export async function getBankConcentration(date: string, limit = 20): Promise<BankConcentration[]> {
  return apiFetch<BankConcentration[]>(`/api/v1/dashboard/bank-concentration?date=${date}&limit=${limit}`);
}

export async function getDestinationBankConcentration(date: string, limit = 20): Promise<BankConcentration[]> {
  return apiFetch<BankConcentration[]>(`/api/v1/dashboard/destination-bank-concentration?date=${date}&limit=${limit}`);
}

export async function getAtmHotspots(date: string, limit = 20): Promise<AtmHotspot[]> {
  return apiFetch<AtmHotspot[]>(`/api/v1/dashboard/atm-hotspots?date=${date}&limit=${limit}`);
}

export async function getLayerDistribution(date: string): Promise<LayerBucket[]> {
  return apiFetch<LayerBucket[]>(`/api/v1/dashboard/layer-distribution?date=${date}`);
}

export async function getAccountsAtLayer(date: string, layer: number, limit = 5000): Promise<LienAccountAtLayer[]> {
  return apiFetch<LienAccountAtLayer[]>(`/api/v1/dashboard/accounts-at-layer?date=${date}&layer=${layer}&limit=${limit}`);
}

export async function getDisposalSummary(date: string): Promise<DisposalSummary> {
  return apiFetch<DisposalSummary>(`/api/v1/dashboard/disposal-summary?date=${date}`);
}

export async function getTrialSummary(date: string): Promise<TrialSummary> {
  return apiFetch<TrialSummary>(`/api/v1/dashboard/trial-summary?date=${date}`);
}

export async function getPendingByYear(date: string): Promise<PendingByYearRow[]> {
  return apiFetch<PendingByYearRow[]>(`/api/v1/dashboard/pending-by-year?date=${date}`);
}

/** FIR Dashboard — per-PS FIR-count leaderboard for a date window.
 *  Registration date drives the window. Admin scoping applies. */
export async function getFirPsPerformance(
  from?: string,
  to?: string,
  financial: FirFinancialFilter = 'all',
): Promise<FirPsPerformanceRow[]> {
  const qs = new URLSearchParams();
  if (from) qs.set('from', from);
  if (to) qs.set('to', to);
  if (financial !== 'all') qs.set('financial', financial);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<FirPsPerformanceRow[]>(`/api/v1/dashboard/fir-ps-performance${suffix}`);
}

/** Deep Analysis -- trace every account touching a single FIR
 *  across all 5 source tables (all_accounts, lien_accounts,
 *  victim_accounts, accused_accounts, money_transfers). Returns
 *  case metadata + a flat list of accounts tagged with source.
 *  Requires ps_id because FIR Nos are only unique per PS -- the
 *  same '0001/2026' can exist at multiple stations.
 *  super_admin only -- 403 for anyone else. */
export async function getAccountsFirTrace(
  firNo: string, psId: number,
): Promise<AccountsFirTrace> {
  const qs = new URLSearchParams({ fir_no: firNo, ps_id: String(psId) });
  return apiFetch<AccountsFirTrace>(
    `/api/v1/dashboard/accounts-fir-trace?${qs.toString()}`,
  );
}

/** Layer 1..15 histogram of accounts, split by KA vs Rest of India,
 *  for the Account Details dashboard's layer-distribution row.
 *  Accounts with NULL branch_state count as Rest. Accounts with
 *  NULL layer come back as separate unknown_layer_ka / _rest counts. */
export async function getAccountsLayerDistribution(
  date: string,
): Promise<AccountsLayerDistribution> {
  return apiFetch<AccountsLayerDistribution>(
    `/api/v1/dashboard/accounts-layer-distribution?date=${encodeURIComponent(date)}`,
  );
}

/** Per-day new-account counts for the Account Details dashboard's
 *  daily-growth line chart. `days` sets the trailing window (default
 *  30). Missing days are zero-filled so the line stays continuous. */
export async function getAccountsDailyGrowth(
  date: string,
  days = 30,
): Promise<AccountsDailyPoint[]> {
  const qs = new URLSearchParams({ date, days: String(days) });
  return apiFetch<AccountsDailyPoint[]>(
    `/api/v1/dashboard/accounts-daily-growth?${qs.toString()}`,
  );
}

/* ── NCRP Dashboard (super_admin only) ─────────────────────────── */

/** KPI cards -- cumulative to the picked date. */
export function getNcrpSummary(date: string): Promise<NcrpKpiSummary> {
  return apiFetch<NcrpKpiSummary>(`/api/v1/dashboard/ncrp-summary?date=${date}`);
}

/** Per-PS mule-report count in [from, to]. Zero-filled for silent PSes. */
export function getNcrpPsComparison(from: string, to: string): Promise<NcrpPsReportCount[]> {
  const qs = new URLSearchParams({ from, to });
  return apiFetch<NcrpPsReportCount[]>(`/api/v1/dashboard/ncrp-ps-comparison?${qs.toString()}`);
}

/** Top-N banks by money_transfer count in [from, to]. */
export function getNcrpTopBanks(from: string, to: string, limit = 10): Promise<NcrpBankConcentration[]> {
  const qs = new URLSearchParams({ from, to, limit: String(limit) });
  return apiFetch<NcrpBankConcentration[]>(`/api/v1/dashboard/ncrp-top-banks?${qs.toString()}`);
}

/** Money-trail layer distribution across money_transfers in [from, to]. */
export function getNcrpLayerDistribution(from: string, to: string): Promise<LayerBucket[]> {
  const qs = new URLSearchParams({ from, to });
  return apiFetch<LayerBucket[]>(`/api/v1/dashboard/ncrp-layer-distribution?${qs.toString()}`);
}

/** Top-N ATM locations by total disputed cash withdrawn in [from, to]. */
export function getNcrpTopAtmLocations(from: string, to: string, limit = 10): Promise<NcrpAtmLocation[]> {
  const qs = new URLSearchParams({ from, to, limit: String(limit) });
  return apiFetch<NcrpAtmLocation[]>(`/api/v1/dashboard/ncrp-top-atm-locations?${qs.toString()}`);
}

/** Repeat Accounts -- super_admin cross-PS aggregation of accounts
 *  registered against >= min_firs distinct FIRs. Call once per
 *  account_type ('Mule' or 'Non-Mule') to show separate tables. */
export function getRepeatAccounts(
  accountType: 'Mule' | 'Non-Mule',
  minFirs = 2,
  limit = 1000,
): Promise<RepeatAccount[]> {
  const qs = new URLSearchParams({
    account_type: accountType,
    min_firs: String(minFirs),
    limit: String(limit),
  });
  return apiFetch<RepeatAccount[]>(`/api/v1/dashboard/repeat-accounts?${qs.toString()}`);
}

/** Drill-down: every FIR + PS + layer the account appeared at. Used
 *  by the Repeat Accounts modal to show cross-FIR layer variance. */
export function getAccountFirHistory(accountNo: string): Promise<AccountFirOccurrence[]> {
  return apiFetch<AccountFirOccurrence[]>(
    `/api/v1/dashboard/account-fir-history?account_no=${encodeURIComponent(accountNo)}`,
  );
}

/** Crypto exchange / asset transactions found in parsed statements.
 *  super_admin only; 403 otherwise. Reads the crypto_txn table built by
 *  analysis/build_crypto.py — detection is never done at request time. */
export async function getCryptoTrail(
  accountType = 'All', evidenceLimit = 60, accountLimit = 500,
): Promise<CryptoTrailSummary> {
  const qs = new URLSearchParams({
    account_type: accountType,
    evidence_limit: String(evidenceLimit),
    account_limit: String(accountLimit),
  });
  return apiFetch<CryptoTrailSummary>(`/api/v1/dashboard/crypto-trail?${qs.toString()}`);
}
