import { apiFetch } from './client';
import type { DsrEntry } from '../../types';

export async function upsertDsr(data: Record<string, unknown>): Promise<DsrEntry> {
  return apiFetch<DsrEntry>('/api/v1/dsr/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getOwnDsr(date: string): Promise<DsrEntry | null> {
  return apiFetch<DsrEntry | null>(`/api/v1/dsr/?date=${date}`);
}

export async function getDsrHistory(limit = 30): Promise<DsrEntry[]> {
  return apiFetch<DsrEntry[]>(`/api/v1/dsr/history?limit=${limit}`);
}

export async function getAllDsr(date: string): Promise<DsrEntry[]> {
  return apiFetch<DsrEntry[]>(`/api/v1/dsr/all?date=${date}`);
}
