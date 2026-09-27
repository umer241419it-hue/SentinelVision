// SentinelVision — authentication service layer.
//
// Talks to the Express bridge (/api/auth/*). The bridge hashes passwords with
// bcryptjs (12 rounds) and returns JWT access tokens; passwords/hashes never
// travel back to the UI. Token is persisted in localStorage (Electron renderer
// is a private context; there are no third parties to leak it to).

export const BRIDGE_BASE_URL = import.meta.env.VITE_BRIDGE_URL || 'http://127.0.0.1:3000';

const TOKEN_KEY = 'sv-token';
const USER_KEY = 'sv-user';

export async function authFetch(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const res = await fetch(`${BRIDGE_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {})
    }
  });
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok) {
    const err = new Error(body?.details || body?.error || `Request failed: ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}

// ---------------------------------------------------------------------------
// Token / persisted user
// ---------------------------------------------------------------------------
export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY)) || null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------
export async function login(email, password) {
  const data = await authFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password })
  });
  setSession(data.token, data.user);
  return data;
}

export async function register({ fullName, email, password, confirmPassword, role }) {
  const data = await authFetch('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ fullName, email, password, confirmPassword, role })
  });
  // Note: registration does NOT log you in — bridge returns no token.
  return data;
}

export async function fetchMe() {
  return authFetch('/api/auth/me');
}

export async function logout() {
  try {
    await authFetch('/api/auth/logout', { method: 'POST' });
  } finally {
    clearSession();
  }
}

// Password strength meter (client-side UX mirror of the bridge's rules:
// >=8 chars, upper, lower, digit — same checks the server enforces).
export function passwordStrength(pw) {
  const checks = [
    { label: '8+ characters', ok: (pw || '').length >= 8 },
    { label: 'Uppercase letter', ok: /[A-Z]/.test(pw || '') },
    { label: 'Lowercase letter', ok: /[a-z]/.test(pw || '') },
    { label: 'Digit', ok: /[0-9]/.test(pw || '') },
    { label: 'Symbol', ok: /[^A-Za-z0-9]/.test(pw || '') }
  ];
  const score = checks.filter((c) => c.ok).length; // 0..5
  const labels = ['WEAK', 'WEAK', 'FAIR', 'GOOD', 'STRONG', 'VERY STRONG'];
  return { score, checks, label: labels[score] };
}
