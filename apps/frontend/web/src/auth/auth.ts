/**
 * OAuth2/OIDC authentication with PKCE.
 */

import { config } from '../config';
import { generateCodeVerifier, generateCodeChallenge, generateState } from './pkce';
import {
  getAuthState,
  setAuthState,
  clearAuthState,
  storePkceVerifier,
  getPkceVerifier,
  storePkceState,
  getPkceState,
  isTokenExpired,
  shouldRefreshToken,
  getTimeUntilExpiry,
  updateTokens,
} from './storage';
import type { TokenResponse, User, AuthState } from './types';

/**
 * Initiate login by redirecting to auth server.
 */
export async function login(returnTo?: string): Promise<void> {
  console.log('[Auth] Starting login flow...');

  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);
  const state = generateState();

  console.log('[Auth] Generated PKCE state:', state);
  console.log('[Auth] Code verifier length:', codeVerifier.length);

  // Store PKCE values for callback
  storePkceVerifier(codeVerifier);
  storePkceState(state);

  // Store return URL
  if (returnTo) {
    sessionStorage.setItem('auth_return_to', returnTo);
  }

  // Build authorization URL
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.clientId,
    redirect_uri: `${window.location.origin}/auth/callback`,
    scope: 'openid profile email',
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });

  const authUrl = `${config.authUrl}/oauth2/authorize?${params}`;
  console.log('[Auth] Redirecting to:', authUrl);

  window.location.href = authUrl;
}

/**
 * Handle OAuth callback and exchange code for tokens.
 */
export async function handleCallback(): Promise<string> {
  console.log('[Auth] Handling callback...');
  console.log('[Auth] Current URL:', window.location.href);

  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');
  const state = params.get('state');
  const error = params.get('error');
  const errorDescription = params.get('error_description');

  console.log('[Auth] Received code:', code ? `${code.substring(0, 10)}...` : 'null');
  console.log('[Auth] Received state:', state);
  console.log('[Auth] Error:', error, errorDescription);

  if (error) {
    console.error('[Auth] Auth error:', error, errorDescription);
    throw new Error(errorDescription || error);
  }

  if (!code) {
    console.error('[Auth] No authorization code received');
    throw new Error('No authorization code received');
  }

  // Verify state
  const storedState = getPkceState();
  console.log('[Auth] Stored state:', storedState);
  console.log('[Auth] State match:', state === storedState);

  if (state !== storedState) {
    console.error('[Auth] State mismatch! Received:', state, 'Stored:', storedState);
    throw new Error('Invalid state parameter');
  }

  // Get code verifier
  const codeVerifier = getPkceVerifier();
  console.log('[Auth] Code verifier found:', !!codeVerifier);

  if (!codeVerifier) {
    console.error('[Auth] No code verifier found in sessionStorage');
    throw new Error('No code verifier found');
  }

  // Exchange code for tokens
  console.log('[Auth] Exchanging code for tokens...');
  const tokenResponse = await exchangeCodeForTokens(code, codeVerifier);
  console.log('[Auth] Token response received:', {
    hasAccessToken: !!tokenResponse.access_token,
    hasIdToken: !!tokenResponse.id_token,
    expiresIn: tokenResponse.expires_in,
    tokenType: tokenResponse.token_type,
  });

  // Store tokens
  const user = tokenResponse.id_token ? parseIdToken(tokenResponse.id_token) : null;
  console.log('[Auth] Parsed user from ID token:', user);

  setAuthState(
    tokenResponse.access_token,
    tokenResponse.expires_in,
    user,
    tokenResponse.refresh_token || null
  );
  console.log('[Auth] Auth state saved to sessionStorage');

  // Verify it was saved
  const savedState = getAuthState();
  console.log('[Auth] Verified saved state:', {
    isAuthenticated: savedState.isAuthenticated,
    hasUser: !!savedState.user,
    hasToken: !!savedState.accessToken,
  });

  // Get return URL
  const returnTo = sessionStorage.getItem('auth_return_to') || '/';
  sessionStorage.removeItem('auth_return_to');
  console.log('[Auth] Returning to:', returnTo);

  return returnTo;
}

/**
 * Exchange authorization code for tokens.
 */
async function exchangeCodeForTokens(
  code: string,
  codeVerifier: string
): Promise<TokenResponse> {
  const tokenUrl = `${config.authUrl}/oauth2/token`;
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: config.clientId,
    code,
    redirect_uri: `${window.location.origin}/auth/callback`,
    code_verifier: codeVerifier,
  });

  console.log('[Auth] Token request URL:', tokenUrl);
  console.log('[Auth] Token request body:', {
    grant_type: 'authorization_code',
    client_id: config.clientId,
    code: `${code.substring(0, 10)}...`,
    redirect_uri: `${window.location.origin}/auth/callback`,
    code_verifier: `${codeVerifier.substring(0, 10)}...`,
  });

  const response = await fetch(tokenUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  });

  console.log('[Auth] Token response status:', response.status);

  if (!response.ok) {
    const errorText = await response.text();
    console.error('[Auth] Token exchange failed:', response.status, errorText);
    let error;
    try {
      error = JSON.parse(errorText);
    } catch {
      error = { error: errorText };
    }
    throw new Error(error.error_description || error.error || 'Token exchange failed');
  }

  const tokenData = await response.json();
  console.log('[Auth] Token exchange successful');
  return tokenData;
}

/**
 * Parse ID token to extract user info.
 */
function parseIdToken(idToken: string): User | null {
  try {
    const parts = idToken.split('.');
    if (parts.length !== 3) return null;

    const payload = JSON.parse(atob(parts[1]));
    return payload as User;
  } catch {
    return null;
  }
}

/**
 * Logout: clear local state and revoke refresh token.
 */
export async function logout(): Promise<void> {
  const state = getAuthState();
  const refreshToken = state.refreshToken;

  // Step 1: Stop token refresh timer
  stopTokenRefreshTimer();

  // Step 2: Clear local auth state
  clearAuthState();
  console.log('[Auth] Local auth state cleared');

  // Step 2: Revoke refresh token on auth server (if we have one)
  if (refreshToken) {
    try {
      const revokeUrl = `${config.authUrl}/oauth2/revoke`;
      const body = new URLSearchParams({
        token: refreshToken,
        token_type_hint: 'refresh_token',
        client_id: config.clientId,
      });

      console.log('[Auth] Revoking refresh token...');
      const response = await fetch(revokeUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body,
      });

      if (response.ok) {
        console.log('[Auth] Refresh token revoked successfully');
      } else {
        console.warn('[Auth] Failed to revoke refresh token:', response.status);
      }
    } catch (error) {
      // Don't block logout if revocation fails
      console.warn('[Auth] Error revoking refresh token:', error);
    }
  }

  // Redirect to home
  window.location.href = '/';
}

// Token refresh timer ID
let refreshTimerId: ReturnType<typeof setTimeout> | null = null;

// Refresh threshold in seconds (refresh 60s before expiry)
const REFRESH_THRESHOLD_SECONDS = 60;

// Minimum refresh interval to prevent rapid retries on error
const MIN_REFRESH_INTERVAL_MS = 5000;

/**
 * Refresh the access token using the refresh token.
 * Returns true if refresh was successful.
 */
export async function refreshAccessToken(): Promise<boolean> {
  const state = getAuthState();

  if (!state.refreshToken) {
    console.log('[Auth] No refresh token available');
    return false;
  }

  try {
    console.log('[Auth] Refreshing access token...');
    const tokenUrl = `${config.authUrl}/oauth2/token`;
    const body = new URLSearchParams({
      grant_type: 'refresh_token',
      client_id: config.clientId,
      refresh_token: state.refreshToken,
    });

    const response = await fetch(tokenUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body,
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('[Auth] Token refresh failed:', response.status, errorText);

      // If refresh token is invalid/expired, clear auth state
      if (response.status === 400 || response.status === 401) {
        console.log('[Auth] Refresh token invalid, clearing auth state');
        clearAuthState();
        stopTokenRefreshTimer();
      }
      return false;
    }

    const tokenData: TokenResponse = await response.json();
    console.log('[Auth] Token refresh successful, new expiry in', tokenData.expires_in, 'seconds');

    // Update tokens (preserves user info)
    updateTokens(
      tokenData.access_token,
      tokenData.expires_in,
      tokenData.refresh_token || null
    );

    // Reschedule next refresh
    scheduleTokenRefresh();

    return true;
  } catch (error) {
    console.error('[Auth] Error refreshing token:', error);
    return false;
  }
}

/**
 * Schedule automatic token refresh before expiration.
 */
export function scheduleTokenRefresh(): void {
  // Clear any existing timer
  stopTokenRefreshTimer();

  const state = getAuthState();
  if (!state.isAuthenticated || !state.refreshToken) {
    console.log('[Auth] Not scheduling refresh: not authenticated or no refresh token');
    return;
  }

  const timeUntilExpiry = getTimeUntilExpiry();
  if (timeUntilExpiry <= 0) {
    console.log('[Auth] Token already expired, attempting immediate refresh');
    refreshAccessToken();
    return;
  }

  // Schedule refresh REFRESH_THRESHOLD_SECONDS before expiry
  const refreshIn = Math.max(
    timeUntilExpiry - REFRESH_THRESHOLD_SECONDS * 1000,
    MIN_REFRESH_INTERVAL_MS
  );

  console.log('[Auth] Scheduling token refresh in', Math.round(refreshIn / 1000), 'seconds');

  refreshTimerId = setTimeout(async () => {
    const success = await refreshAccessToken();
    if (!success && getAuthState().isAuthenticated) {
      // Retry with shorter interval if still authenticated
      console.log('[Auth] Refresh failed, will retry shortly');
      refreshTimerId = setTimeout(() => refreshAccessToken(), MIN_REFRESH_INTERVAL_MS);
    }
  }, refreshIn);
}

/**
 * Stop the automatic token refresh timer.
 */
export function stopTokenRefreshTimer(): void {
  if (refreshTimerId !== null) {
    clearTimeout(refreshTimerId);
    refreshTimerId = null;
    console.log('[Auth] Token refresh timer stopped');
  }
}

/**
 * Get current access token if valid.
 * Optionally triggers refresh if token is about to expire.
 */
export function getAccessToken(): string | null {
  const state = getAuthState();
  if (!state.isAuthenticated || isTokenExpired()) {
    return null;
  }

  // Check if we should proactively refresh
  if (shouldRefreshToken(REFRESH_THRESHOLD_SECONDS) && state.refreshToken) {
    // Trigger async refresh but return current token
    refreshAccessToken();
  }

  return state.accessToken;
}

/**
 * Check if user is authenticated.
 */
export function isAuthenticated(): boolean {
  const state = getAuthState();
  return state.isAuthenticated && !isTokenExpired();
}

/**
 * Get current user.
 */
export function getUser(): User | null {
  return getAuthState().user;
}

/**
 * Get full auth state.
 */
export { getAuthState };
export type { AuthState, User, TokenResponse };
