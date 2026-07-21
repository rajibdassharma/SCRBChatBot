import { apiFetch } from './client';
import type {
  PortalsDsrEntry, PortalsDsrListItem, PortalsDsrStatus, PortalsDsrWritePayload,
} from '../../types';

/** Create a Portals DSR entry. Server fills unit_id + ps_id from JWT,
 *  submitted_by, timestamps. Payload can be partial (any metric fields
 *  the operator hasn't filled default to 0 server-side). */
export function createPortalsDsr(payload: PortalsDsrWritePayload) {
  return apiFetch<PortalsDsrEntry>('/api/v1/portals-dsr', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updatePortalsDsr(id: string, payload: PortalsDsrWritePayload) {
  return apiFetch<PortalsDsrEntry>(`/api/v1/portals-dsr/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function getPortalsDsr(id: string) {
  return apiFetch<PortalsDsrEntry>(`/api/v1/portals-dsr/${id}`);
}

export function deletePortalsDsr(id: string) {
  return apiFetch<{ ok: boolean }>(`/api/v1/portals-dsr/${id}`, { method: 'DELETE' });
}

/** PS-scoped list, newest first. Optional date-window + status filter. */
export function listPortalsDsr(opts: {
  from?: string;
  to?: string;
  status?: PortalsDsrStatus;
  limit?: number;
  offset?: number;
} = {}) {
  const params = new URLSearchParams();
  if (opts.from)   params.set('from', opts.from);
  if (opts.to)     params.set('to',   opts.to);
  if (opts.status) params.set('status', opts.status);
  if (opts.limit  != null) params.set('limit',  String(opts.limit));
  if (opts.offset != null) params.set('offset', String(opts.offset));
  const qs = params.toString();
  return apiFetch<PortalsDsrListItem[]>(
    `/api/v1/portals-dsr${qs ? `?${qs}` : ''}`,
  );
}
