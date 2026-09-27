import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import {
  login as apiLogin,
  register as apiRegister,
  logout as apiLogout,
  fetchMe,
  getToken,
  getStoredUser,
  clearSession
} from '../services/authApi';

/**
 * AuthContext — holds the authenticated user + session status.
 * On mount, any persisted token is re-validated against GET /api/auth/me.
 */
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    let live = true;
    async function boot() {
      if (!getToken()) {
        setBooting(false);
        return;
      }
      try {
        const me = await fetchMe();
        if (live) setUser(me.user);
      } catch {
        // Invalid/expired token or unreachable bridge → force re-login.
        clearSession();
      } finally {
        if (live) setBooting(false);
      }
    }
    boot();
    return () => {
      live = false;
    };
  }, []);

  const value = useMemo(
    () => ({
      user,
      booting,
      async login(email, password) {
        const data = await apiLogin(email, password);
        setUser(data.user);
        return data;
      },
      async register(payload) {
        return apiRegister(payload);
      },
      async logout() {
        await apiLogout();
        setUser(null);
      }
    }),
    [user, booting]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
