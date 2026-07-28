export function formatINR(amount: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat('en-IN').format(n);
}

/** Format a Date as `YYYY-MM-DD` using its LOCAL components.
 *
 *  Do NOT use `.toISOString().slice(0,10)` -- that converts to UTC
 *  and drops back a day for any local midnight in a +HH:MM zone
 *  (IST midnight = previous UTC day at 18:30). Every "yesterday's
 *  data" and "today's cutoff" helper in this app was silently
 *  reporting one day early, worst around midnight IST. */
export function localISO(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Today's date in the browser's LOCAL zone as YYYY-MM-DD. */
export function todayISO(): string {
  return localISO(new Date());
}

/** Yesterday's date in the browser's LOCAL zone as YYYY-MM-DD. */
export function yesterdayISO(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return localISO(d);
}

/** Today minus `n` days, in the browser's LOCAL zone, as YYYY-MM-DD.
 *  Positive `n` goes backwards (e.g. `isoDaysAgo(29)` for a 30-day
 *  window ending today). */
export function isoDaysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return localISO(d);
}

/** Add / subtract days from an existing YYYY-MM-DD string, returning
 *  a YYYY-MM-DD string in the LOCAL zone. Parses the input as local
 *  midnight so the shift is clean.  */
export function isoAddDays(dateIso: string, days: number): string {
  const [y, m, d] = dateIso.split('-').map(Number);
  const dt = new Date(y, (m || 1) - 1, d || 1);
  dt.setDate(dt.getDate() + days);
  return localISO(dt);
}
