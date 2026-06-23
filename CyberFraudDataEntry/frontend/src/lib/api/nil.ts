import { apiFetch } from './client';
import type { NilDeclaration, NilDeclarationCreatePayload } from '../../types';

/** Mark a date (defaults to today server-side) as NIL for the caller's PS.
 *  Idempotent — re-declaring is a no-op, returns the existing row. */
export async function declareNil(body: NilDeclarationCreatePayload = {}): Promise<NilDeclaration> {
  return apiFetch<NilDeclaration>('/api/v1/nil/declare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/** Has the caller's PS already declared NIL for today? null if not. */
export async function getNilToday(): Promise<NilDeclaration | null> {
  return apiFetch<NilDeclaration | null>('/api/v1/nil/today');
}
