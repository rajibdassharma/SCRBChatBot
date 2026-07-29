import { apiFetch } from './client';
import type {
  KpiSummary, UnitComparison, PsComparison, SubmissionStatus, TrendPoint,
  QuietUnit, TimeToArrestRow, BankSlaRow,
  RecurringAccount, BankConcentration, AtmHotspot, LayerBucket, LienAccountAtLayer,
  AccountCaseDetail, CaseDetailFull,
  DisposalSummary, TrialSummary, PendingByYearRow,
  AccountsKpiSummary, AccountsPsComparison, AccountsBankConcentration,
  AllAccount,
  PortalsDsrKpiSummary, PortalsDsrPsComparison,
  FirPsPerformanceRow,
  AccountsDailyPoint, AccountsLayerDistribution,
} from '../../types';

/** All Accounts dashboard — KPI cards + per-PS comparison. */
export async function getAccountsSummary(date: string): Promise<AccountsKpiSummary> {
  return apiFetch<AccountsKpiSummary>(`/api/v1/dashboard/accounts-summary?date=${date}`);
}

export async function getAccountsComparison(date: string): Promise<AccountsPsComparison[]> {
  return apiFetch<AccountsPsComparison[]>(`/api/v1/dashboard/accounts-comparison?date=${date}`);
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

export async function getRecurringAccounts(date: string, minCases = 2, limit = 50): Promise<RecurringAccount[]> {
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

export async function getAccountsAtLayer(date: string, layer: number, limit = 200): Promise<LienAccountAtLayer[]> {
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
): Promise<FirPsPerformanceRow[]> {
  const qs = new URLSearchParams();
  if (from) qs.set('from', from);
  if (to) qs.set('to', to);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<FirPsPerformanceRow[]>(`/api/v1/dashboard/fir-ps-performance${suffix}`);
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
