import { apiFetch } from './client';
import type {
  DailyWorkDashboard, DailyWorkEntry, DailyWorkWritePayload,
} from '../../types';

/** POST — upsert on (unit_id, ps_id, fir_no, report_date). */
export async function upsertDailyWork(
  data: DailyWorkWritePayload,
): Promise<DailyWorkEntry> {
  return apiFetch<DailyWorkEntry>('/api/v1/daily-work/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/** GET one row by (fir_no, date) — returns null if the operator hasn't
 *  logged that FIR on that date yet. Used by the entry page to prefill
 *  when the operator picks an existing FIR + date. */
export async function getOwnDailyWork(
  firNo: string,
  date: string,
): Promise<DailyWorkEntry | null> {
  const qs = new URLSearchParams({ fir_no: firNo, date });
  return apiFetch<DailyWorkEntry | null>(`/api/v1/daily-work/?${qs.toString()}`);
}

/** GET all daily-work rows for one FIR at this PS, newest first.
 *  Powers the Update / History screen once the operator types an FIR. */
export async function getDailyWorkByFir(firNo: string): Promise<DailyWorkEntry[]> {
  const qs = new URLSearchParams({ fir_no: firNo });
  return apiFetch<DailyWorkEntry[]>(`/api/v1/daily-work/by-fir?${qs.toString()}`);
}

/** GET most recent N rows across all FIRs for this PS.
 *  Powers the "recent activity" list on the Update page landing. */
export async function getDailyWorkHistory(limit = 30): Promise<DailyWorkEntry[]> {
  return apiFetch<DailyWorkEntry[]>(`/api/v1/daily-work/history?limit=${limit}`);
}

/** GET one row by id. Used when the update page navigates
 *  `/daily-work/:id` to open a specific row in edit mode. */
export async function getDailyWorkById(id: number): Promise<DailyWorkEntry> {
  return apiFetch<DailyWorkEntry>(`/api/v1/daily-work/${id}`);
}

export async function deleteDailyWork(id: number): Promise<void> {
  await apiFetch<void>(`/api/v1/daily-work/${id}`, { method: 'DELETE' });
}

/** Admin-only aggregation. `from` / `to` are ISO dates (YYYY-MM-DD).
 *  Omit both to get the trailing-30-day window. */
export async function getDailyWorkDashboard(
  from?: string,
  to?: string,
): Promise<DailyWorkDashboard> {
  const qs = new URLSearchParams();
  if (from) qs.set('from', from);
  if (to) qs.set('to', to);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<DailyWorkDashboard>(`/api/v1/daily-work/dashboard${suffix}`);
}
