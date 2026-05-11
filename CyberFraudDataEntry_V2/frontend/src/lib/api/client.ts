const BASE = import.meta.env.VITE_API_BASE ?? '';

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('token');
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (options.body && typeof options.body === 'string') {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const message = err.detail || `HTTP ${res.status}`;

    if (res.status === 401) {
      // Don't redirect on login, change-password, or logout responses —
      // those are either the user actively authenticating, or actively
      // ending their session (a 401 on logout just means "token already
      // invalid", which is the desired end state).
      const isAuthEndpoint =
        path.includes('/auth/login') ||
        path.includes('/auth/change-password') ||
        path.includes('/auth/logout');
      if (!isAuthEndpoint) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login';
      }
      throw new Error(message);
    }

    throw new Error(message);
  }

  if (res.status === 204 || res.headers.get('content-length') === '0') {
    return null as T;
  }

  return res.json();
}
