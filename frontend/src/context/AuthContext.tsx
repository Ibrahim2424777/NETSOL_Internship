// Auth state and actions for the whole app. Login persistence works like
// this: the access token lives only in memory (see authStore.ts) - a page
// refresh loses it immediately. What survives a refresh (or the browser
// closing and reopening) is the secure, HTTP-only refresh cookie the
// backend set on login, which JS can never read directly. So on every app
// load, before rendering anything that depends on auth state, this
// provider makes one silent call to /auth/refresh: if that cookie is still
// valid, it comes back with a fresh access token and the user is
// transparently still logged in; if not, they land on the login page.
// That single request is what "remain logged in after closing the browser"
// actually is - not any client-side storage of the token itself.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';

import { buildGoogleAuthUrl, exchangeGoogleCode, logout as logoutApi } from '../services/authApi';
import { refreshAccessToken } from '../services/authRefresh';
import { clearAuthState, getAuthState, setAuthState, subscribeAuthState } from '../services/authStore';
import type { User } from '../types';

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  loginWithGoogle: () => void;
  completeGoogleLogin: (code: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { accessToken, user } = useSyncExternalStore(subscribeAuthState, getAuthState);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    refreshAccessToken().finally(() => setIsLoading(false));
  }, []);

  const loginWithGoogle = useCallback(() => {
    window.location.href = buildGoogleAuthUrl();
  }, []);

  const completeGoogleLogin = useCallback(async (code: string) => {
    // exchangeGoogleCode (authApi.ts) is a pure "talk to the backend"
    // function with no state side effects - writing the result to the
    // shared store is this context's job, same as refreshAccessToken does
    // for the silent-refresh path.
    const { access_token, user: loggedInUser } = await exchangeGoogleCode(code);
    setAuthState({ accessToken: access_token, user: loggedInUser });
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutApi();
    } finally {
      clearAuthState();
    }
  }, []);

  // Every consumer of useAuth() (which is most of the app - the navbar, every
  // protected route, the chat page) re-renders whenever this object is a new
  // reference, even if nothing it actually reads changed. Without this memo,
  // that's every single AuthProvider render, since a fresh object literal
  // was built each time regardless. The loginWithGoogle/completeGoogleLogin/
  // logout functions are already stable (useCallback with no deps), so this
  // only actually produces a new reference when user, accessToken, or
  // isLoading themselves change.
  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: Boolean(accessToken && user),
      isLoading,
      loginWithGoogle,
      completeGoogleLogin,
      logout,
    }),
    [user, accessToken, isLoading, loginWithGoogle, completeGoogleLogin, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
