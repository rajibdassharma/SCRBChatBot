import { apiFetch } from './client';
import type { KpiSummary, UnitComparison, SubmissionStatus, TrendPoint } from '../../types';

export async function getSummary(date: string): Promise<KpiSummary> {
  return apiFetch<KpiSummary>(`/api/v1/dashboard/summary?date=${date}`);
}

export async function getUnitComparison(date: string): Promise<UnitComparison[]> {
  return apiFetch<UnitComparison[]>(`/api/v1/dashboard/unit-comparison?date=${date}`);
}

export async function getTrends(from: string, to: string): Promise<TrendPoint[]> {
  return apiFetch<TrendPoint[]>(`/api/v1/dashboard/trends?from=${from}&to=${to}`);
}

export async function getSubmissionStatus(date: string): Promise<SubmissionStatus[]> {
  return apiFetch<SubmissionStatus[]>(`/api/v1/dashboard/submission-status?date=${date}`);
}
