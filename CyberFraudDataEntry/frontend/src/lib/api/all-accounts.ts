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

/** PS-scoped list with optional filters:
 *  - `q`: free-text search across account/holder/FIR/ack
 *  - `firNo`: exact FIR filter (variant-matched for legacy zero-padding)
 *  - `psId`: super_admin-only cross-PS drill; ignored for other roles
 *  - `accountType`: Victim / Mule / Non-Mule
 */
export function listAllAccounts(opts: {
  q?: string;
  firNo?: string;
  psId?: number;
  accountType?: 'Victim' | 'Mule' | 'Non-Mule';
  limit?: number;
  offset?: number;
} = {}) {
  const params = new URLSearchParams();
  if (opts.q) params.set('q', opts.q);
  if (opts.firNo) params.set('fir_no', opts.firNo);
  if (opts.psId != null) params.set('ps_id', String(opts.psId));
  if (opts.accountType) params.set('account_type', opts.accountType);
  if (opts.limit != null) params.set('limit', String(opts.limit));
  if (opts.offset != null) params.set('offset', String(opts.offset));
  const qs = params.toString();
  return apiFetch<AllAccountListItem[]>(
    `/api/v1/all-accounts${qs ? `?${qs}` : ''}`,
  );
}
