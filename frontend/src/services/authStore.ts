// A tiny external (non-React) store for the access token and current user.
//
// Why this exists: the Axios interceptor needs to read the current token
// (to attach it to every request) and write a new one (after a silent
// refresh) from plain JS, outside of any component's render cycle. Putting
// this state in React Context alone wouldn't let non-component code reach
// it without awkward workarounds. AuthContext (see src/context/AuthContext.tsx)
// subscribes to this same store via useSyncExternalStore, so React state and
// what the interceptor sees are always exactly the same thing, never two
// copies that can drift apart.
import type { User } from '../types';

export interface AuthState {
  accessToken: string | null;
  user: User | null;
}

let state: AuthState = { accessToken: null, user: null };
const listeners = new Set<() => void>();

export function getAuthState(): AuthState {
  return state;
}

export function setAuthState(next: AuthState): void {
  state = next;
  listeners.forEach((listener) => listener());
}

export function clearAuthState(): void {
  setAuthState({ accessToken: null, user: null });
}

export function subscribeAuthState(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
