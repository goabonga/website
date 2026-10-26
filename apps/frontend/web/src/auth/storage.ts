/**
 * Token storage using sessionStorage (persists across page reloads within session).
 */

import type { AuthState, User } from './types';

// Storage keys
const AUTH_STATE_KEY = 'auth_state';
const PKCE_VERIFIER_KEY = 'pkce_code_verifier';
const PKCE_STATE_KEY = 'pkce_state';

/**
 * Get current auth state from sessionStorage.
 */
export function getAuthState(): AuthState {
  try {
    const stored = sessionStorage.getItem(AUTH_STATE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch {
    // Invalid JSON, clear it
    sessionStorage.removeItem(AUTH_STATE_KEY);
  }
  return {
    isAuthenticated: false,
    user: null,
    accessToken: null,
    refreshToken: null,
    expiresAt: null,
  };
}

/**
 * Set auth state after successful login.
 */
export function setAuthState(
  accessToken: string,
  expiresIn: number,
  user: User | null = null,
  refreshToken: string | null = null
): void {
  const state: AuthState = {
    isAuthenticated: true,
    user,
    accessToken,
    refreshToken,
    expiresAt: Date.now() + expiresIn * 1000,
  };
  sessionStorage.setItem(AUTH_STATE_KEY, JSON.stringify(state));
}

/**
 * Clear auth state on logout.
 */
export function clearAuthState(): void {
  sessionStorage.removeItem(AUTH_STATE_KEY);
}

/**
 * Check if token is expired.
 */
export function isTokenExpired(): boolean {
  const state = getAuthState();
  if (!state.expiresAt) return true;
  return Date.now() >= state.expiresAt;
}

/**
 * Check if token needs refresh (expires within threshold).
 * Default threshold is 60 seconds before expiration.
 */
export function shouldRefreshToken(thresholdSeconds: number = 60): boolean {
  const state = getAuthState();
  if (!state.expiresAt || !state.refreshToken) return false;
  // Refresh if token expires within threshold
  return Date.now() >= state.expiresAt - thresholdSeconds * 1000;
}

/**
 * Get time until token expires in milliseconds.
 * Returns 0 if already expired or no expiration set.
 */
export function getTimeUntilExpiry(): number {
  const state = getAuthState();
  if (!state.expiresAt) return 0;
  const remaining = state.expiresAt - Date.now();
  return remaining > 0 ? remaining : 0;
}

/**
 * Update tokens after refresh (preserves user info).
 */
export function updateTokens(
  accessToken: string,
  expiresIn: number,
  refreshToken: string | null = null
): void {
  const currentState = getAuthState();
  const state: AuthState = {
    isAuthenticated: true,
    user: currentState.user,
    accessToken,
    refreshToken: refreshToken || currentState.refreshToken,
    expiresAt: Date.now() + expiresIn * 1000,
  };
  sessionStorage.setItem(AUTH_STATE_KEY, JSON.stringify(state));
}

/**
 * Store PKCE verifier in sessionStorage.
 */
export function storePkceVerifier(verifier: string): void {
  sessionStorage.setItem(PKCE_VERIFIER_KEY, verifier);
}

/**
 * Get and clear PKCE verifier from sessionStorage.
 */
export function getPkceVerifier(): string | null {
  const verifier = sessionStorage.getItem(PKCE_VERIFIER_KEY);
  sessionStorage.removeItem(PKCE_VERIFIER_KEY);
  return verifier;
}

/**
 * Store PKCE state in sessionStorage.
 */
export function storePkceState(state: string): void {
  sessionStorage.setItem(PKCE_STATE_KEY, state);
}

/**
 * Get and clear PKCE state from sessionStorage.
 */
export function getPkceState(): string | null {
  const state = sessionStorage.getItem(PKCE_STATE_KEY);
  sessionStorage.removeItem(PKCE_STATE_KEY);
  return state;
}
