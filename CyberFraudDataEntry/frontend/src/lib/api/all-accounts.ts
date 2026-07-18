import { apiFetch } from './client';
import type { AllAccount, AllAccountListItem, AllAccountWritePayload } from '../../types';

/** Create an account. Server assigns serial_no (per-PS max+1) and
 *  fills unit_id + ps_id from the caller's JWT. */
export function createAllAccount(payload: AllAccountWritePayload) {
  return apiFetch<AllAccount>('/api/v1/all-accounts', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateAllAccount(id: string, payload: AllAccountWritePayload) {
  return apiFetch<AllAccount>(`/api/v1/all-accounts/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function getAllAccount(id: string) {
  return apiFetch<AllAccount>(`/api/v1/all-accounts/${id}`);
}

export function deleteAllAccount(id: string) {
  return apiFetch<{ ok: boolean }>(`/api/v1/all-accounts/${id}`, { method: 'DELETE' });
}

/** PS-scoped list with optional free-text search + type filter. */
export function listAllAccounts(opts: {
  q?: string;
  accountType?: 'Victim' | 'Mule';
  limit?: number;
  offset?: number;
} = {}) {
  const params = new URLSearchParams();
  if (opts.q) params.set('q', opts.q);
  if (opts.accountType) params.set('account_type', opts.accountType);
  if (opts.limit != null) params.set('limit', String(opts.limit));
  if (opts.offset != null) params.set('offset', String(opts.offset));
  const qs = params.toString();
  return apiFetch<AllAccountListItem[]>(
    `/api/v1/all-accounts${qs ? `?${qs}` : ''}`,
  );
}
