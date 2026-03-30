import { apiFetch } from './client';
import type { MuleEntry } from '../../types';

export async function upsertMule(data: Record<string, unknown>): Promise<MuleEntry> {
  return apiFetch<MuleEntry>('/api/v1/mule/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getOwnMule(date: string): Promise<MuleEntry | null> {
  return apiFetch<MuleEntry | null>(`/api/v1/mule/?date=${date}`);
}

export async function getMuleHistory(limit = 30): Promise<MuleEntry[]> {
  return apiFetch<MuleEntry[]>(`/api/v1/mule/history?limit=${limit}`);
}

export async function getAllMule(date: string): Promise<MuleEntry[]> {
  return apiFetch<MuleEntry[]>(`/api/v1/mule/all?date=${date}`);
}
