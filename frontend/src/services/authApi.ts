import apiClient from './apiClient';
import type { TokenResponse, User } from '../types';

export function buildGoogleAuthUrl(): string {
  const params = new URLSearchParams({
    client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
    redirect_uri: import.meta.env.VITE_GOOGLE_REDIRECT_URI,
    response_type: 'code',
    scope: 'openid email profile',
    // Forces the account chooser instead of silently reusing whatever
    // Google session happens to already be active in the browser.
    prompt: 'select_account',
  });
  return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

export async function exchangeGoogleCode(code: string): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/google', {
    code,
    redirect_uri: import.meta.env.VITE_GOOGLE_REDIRECT_URI,
  });
  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout');
}

export async function fetchCurrentUser(): Promise<User> {
  const { data } = await apiClient.get<User>('/auth/me');
  return data;
}
