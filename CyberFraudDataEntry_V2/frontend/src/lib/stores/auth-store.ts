import { create } from 'zustand';
import type { User } from '../../types';
import { logoutApi } from '../api/auth';

interface AuthState {
  token: string | null;
  user: User | null;
  setAuth: (token: string, user: User) => void;
  logout: () => Promise<void>;
  loadFromStorage: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,

  setAuth: (token, user) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
    set({ token, user });
  },

  logout: async () => {
    // Best-effort server-side revocation. Skip the API call entirely if
    // there's no token to begin with (otherwise we'd 401 in an endless
    // loop). If the call fails for any reason, still clear local state —
    // the user intends to be logged out.
    const hadToken = !!localStorage.getItem('token');
    if (hadToken) {
      try {
        await logoutApi();
      } catch {
        // ignore — clearing local state is still required
      }
    }
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    set({ token: null, user: null });
  },

  loadFromStorage: () => {
    const token = localStorage.getItem('token');
    const raw = localStorage.getItem('user');
    if (token && raw) {
      try {
        const user = JSON.parse(raw) as User;
        set({ token, user });
      } catch {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
      }
    }
  },
}));
