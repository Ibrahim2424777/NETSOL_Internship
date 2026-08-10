// Shared silent-refresh logic, used by both apiClient's response interceptor
// (for normal JSON requests) and chatStream's fetch-based SSE call (for the
// one endpoint that doesn't go through Axios - see chatStream.ts).
//
// Uses a bare axios call rather than the configured `apiClient` instance
// deliberately, to avoid a circular import (apiClient's own interceptor
// depends on this module).
//
// The single in-flight promise is important, not just tidy: the backend's
// refresh token is single-use (see backend/app/services/auth_service.py -
// every refresh rotates to a new token and revokes the old one). If two
// requests 401 around the same time and each called /auth/refresh
// independently, the second call would be rejected as "already used" even
// though the first one succeeded, incorrectly logging the user out. Routing
// every concurrent refresh attempt through the same promise means exactly
// one network call happens no matter how many requests needed it.
import axios from 'axios';

import { clearAuthState, setAuthState } from './authStore';
import type { TokenResponse } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

let refreshPromise: Promise<string | null> | null = null;

export function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = axios
      .post<TokenResponse>(`${API_BASE_URL}/auth/refresh`, null, { withCredentials: true })
      .then((response) => {
        setAuthState({ accessToken: response.data.access_token, user: response.data.user });
        return response.data.access_token;
      })
      .catch(() => {
        clearAuthState();
        return null;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}
