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
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    // FastAPI returns Pydantic validation errors as `detail: [{loc, msg, type, ...}]`.
    // Prior to this fix, passing that array to `new Error()` produced a `.message`
    // of `[object Object]`, which surfaced verbatim in toasts. Extract a
    // human-readable string per shape.
    let message: string;
    const detail = body?.detail;
    if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail
        .map((e: { loc?: (string | number)[]; msg?: string }) => {
          const loc = Array.isArray(e.loc)
            ? e.loc.filter((x) => x !== 'body').join('.')
            : '';
          const msg = e.msg ?? 'invalid value';
          return loc ? `${loc}: ${msg}` : msg;
        })
        .join('; ');
    } else if (detail && typeof detail === 'object') {
      message = JSON.stringify(detail);
    } else {
      message = `HTTP ${res.status}`;
    }

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
