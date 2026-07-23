/** Role predicates — the source of truth for what each role can do in
 *  the UI. Kept as tiny helpers so the intent reads at the call site
 *  (`isReadOnlyRole(user)` beats `user?.role === 'super_admin'`).
 *
 *  As of 2026-07-23: super_admin (Senior Officer) is view-only across
 *  every module that surfaces FIRs / cases. The backend enforces this
 *  independently (see api/routes_case.py); these helpers just keep
 *  the frontend from OFFERING mutation controls the server would 403.
 */
import type { User } from '../../types';

/** True when the caller is a Senior Officer — cross-PS view rights
 *  but no create / update / delete on any FIR-touching entity. */
export function isSuperAdmin(user: User | null | undefined): boolean {
  return user?.role === 'super_admin';
}

/** Alias reading nicer in JSX / prop names. Same as isSuperAdmin
 *  today; if we ever add other view-only roles they belong here. */
export function isReadOnlyRole(user: User | null | undefined): boolean {
  return isSuperAdmin(user);
}
