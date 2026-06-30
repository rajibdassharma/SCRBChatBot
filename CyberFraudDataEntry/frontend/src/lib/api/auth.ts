import { apiFetch } from './client';
import type { LoginResponse, User } from '../../types';

export async function login(username: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export async function getMe(): Promise<User> {
  return apiFetch<User>('/api/v1/auth/me');
}

export async function logoutApi(): Promise<{ok: boolean; message: string}> {
  return apiFetch('/api/v1/auth/logout', { method: 'POST' });
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<{ok: boolean; message: string}> {
  return apiFetch('/api/v1/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export async function getDistrictsPublic(): Promise<{name: string}[]> {
  const base = import.meta.env.VITE_API_BASE ?? '';
  const res = await fetch(`${base}/api/v1/districts/public`);
  if (!res.ok) throw new Error('Failed to load districts');
  return res.json();
}

export async function getPoliceStationsPublic(district: string): Promise<{id: number, district_name: string, station_name: string, has_super_admin: boolean}[]> {
  const base = import.meta.env.VITE_API_BASE ?? '';
  const res = await fetch(`${base}/api/v1/police-stations/public?district=${encodeURIComponent(district)}`);
  if (!res.ok) throw new Error('Failed to load police stations');
  return res.json();
}

/** Public — fetch the list of active usernames at a given PS so the
 *  login form can show a dropdown. Returned ordered super_admin →
 *  admin → unit_user. Username is the login identifier; role is shown
 *  inline so operators know which one is theirs. */
export async function getUsersForPSPublic(ps_id: number): Promise<{username: string; role: string}[]> {
  const base = import.meta.env.VITE_API_BASE ?? '';
  const res = await fetch(`${base}/api/v1/users/public?ps_id=${ps_id}`);
  if (!res.ok) throw new Error('Failed to load users for police station');
  return res.json();
}
