import { apiFetch } from './client';
import type {
  ManagedUser,
  UserCreatePayload,
  UserUpdatePayload,
  UserCreateResponse,
  PasswordResetResponse,
  UserCount,
} from '../../types';

/** PS-admin only routes — backend gate: require_ps_admin (admin role + ps_id). */

export function listUsers(): Promise<ManagedUser[]> {
  return apiFetch<ManagedUser[]>('/api/v1/users');
}

export function getUserCount(): Promise<UserCount> {
  return apiFetch<UserCount>('/api/v1/users/_count');
}

export function createUser(body: UserCreatePayload): Promise<UserCreateResponse> {
  return apiFetch<UserCreateResponse>('/api/v1/users', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function updateUser(id: number, body: UserUpdatePayload): Promise<ManagedUser> {
  return apiFetch<ManagedUser>(`/api/v1/users/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function deactivateUser(id: number): Promise<ManagedUser> {
  return apiFetch<ManagedUser>(`/api/v1/users/${id}/deactivate`, { method: 'POST' });
}

export function activateUser(id: number): Promise<ManagedUser> {
  return apiFetch<ManagedUser>(`/api/v1/users/${id}/activate`, { method: 'POST' });
}

export function resetPassword(id: number): Promise<PasswordResetResponse> {
  return apiFetch<PasswordResetResponse>(`/api/v1/users/${id}/reset-password`, {
    method: 'POST',
  });
}
