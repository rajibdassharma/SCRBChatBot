/** Shared FIR No. format helpers — source of truth for every FIR
 *  entry field across the app.
 *
 *  Rule (see memory `fir-no-format-xxxx-yyyy`): every FIR entry
 *  field must match `XXXX/YYYY` — exactly 4 digits, slash, 4-digit
 *  year. Leading zeros are expected (`0001/2026`). Matches the
 *  convention already established on AllAccountEntryPage, which
 *  used the same regex before this util existed. Search boxes
 *  (Cases → Update, Daily Work → Update) stay permissive so
 *  operators can type prefixes.
 *
 *  Adding a new FIR entry field? Import `validateFirNo` and render
 *  its return value as an inline error. Pair the field with the
 *  placeholder `FIR_NO_PLACEHOLDER` so operators see the expected
 *  shape before they type. */
export const FIR_NO_RE = /^\d{4}\/\d{4}$/;
export const FIR_NO_PLACEHOLDER = 'e.g. 0001/2026';
export const FIR_NO_FORMAT_HINT = 'Format: XXXX/YYYY (e.g. 0001/2026)';

/** Return an error message when `v` is a non-empty invalid FIR, or
 *  null if `v` is empty or well-formed. Empty is treated as "not
 *  yet typed" — the caller decides whether to also require the field
 *  (e.g. Save-button gate). Whitespace is trimmed before checking. */
export function validateFirNo(v: string): string | null {
  const s = v.trim();
  if (s === '') return null;
  if (!FIR_NO_RE.test(s)) return `Invalid FIR No. ${FIR_NO_FORMAT_HINT}`;
  return null;
}
