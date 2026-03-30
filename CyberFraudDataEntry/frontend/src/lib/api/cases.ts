import { apiFetch } from './client';
import type { CaseEntry, CaseListItem } from '../../types';

export async function createCase(data: CaseEntry): Promise<CaseEntry> {
  return apiFetch<CaseEntry>('/api/v1/cases/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateCase(id: number, data: CaseEntry): Promise<CaseEntry> {
  return apiFetch<CaseEntry>(`/api/v1/cases/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function getCase(id: number): Promise<CaseEntry> {
  return apiFetch<CaseEntry>(`/api/v1/cases/${id}`);
}

export async function listCases(limit = 50, offset = 0): Promise<CaseListItem[]> {
  return apiFetch<CaseListItem[]>(`/api/v1/cases/?limit=${limit}&offset=${offset}`);
}

export async function deleteCase(id: number): Promise<void> {
  return apiFetch<void>(`/api/v1/cases/${id}`, { method: 'DELETE' });
}

export async function listAllCases(limit = 50, offset = 0): Promise<CaseListItem[]> {
  return apiFetch<CaseListItem[]>(`/api/v1/cases/all?limit=${limit}&offset=${offset}`);
}

export async function searchCaseByFir(firNo: string): Promise<CaseEntry | null> {
  return apiFetch<CaseEntry | null>(`/api/v1/cases/search?fir_no=${encodeURIComponent(firNo)}`);
}

export async function searchCaseByPetition(petitionNo: string): Promise<CaseEntry | null> {
  return apiFetch<CaseEntry | null>(`/api/v1/cases/search-petition?petition_no=${encodeURIComponent(petitionNo)}`);
}
