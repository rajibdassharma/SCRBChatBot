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

/** Bank name reduced to a grouping key: whitespace collapsed, upper-cased.
 *
 *  Measured 2026-08-21 on 2,260 distinct stored bank names: 327 of them
 *  differ from another only by case or by runs of spaces. "Axis Bank"
 *  appears in 6 spellings across 3,128 accounts; State Bank of India in
 *  9 across 1,019. Any sum or count grouped on the raw column splits
 *  those silently, which is what an external review of the exported
 *  workbook flagged.
 *
 *  DELIBERATELY CONSERVATIVE. It folds case and spacing and nothing
 *  else -- no fuzzy matching, no abbreviation expansion, no "Ltd"
 *  stripping. Those need a curated bank list and a human decision per
 *  entry; guessing there merges banks that are genuinely different.
 *  1,933 keys remain, well above India's real bank count, and the rest
 *  is entry-quality work with an audit trail, not a display concern.
 *
 *  Used for the EXPORT column only. The screen keeps what the operator
 *  typed -- see the Branch district treatment for the same rule:
 *  entered and derived stay distinguishable. */
export function bankKey(name: string | null | undefined): string {
  return (name ?? '').replace(/\s+/g, ' ').trim().toUpperCase();
}
