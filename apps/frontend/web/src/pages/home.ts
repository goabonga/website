/**
 * Home page component.
 */

import { isAuthenticated, getAuthState } from '../auth';
import { userMenu, mountUserMenu, chatBox, mountChatBox } from '../components';

export function homePage(): string {
  const authenticated = isAuthenticated();
  const authState = getAuthState();

  console.log('[Home] Page loaded');
  console.log('[Home] isAuthenticated:', authenticated);
  console.log('[Home] Auth state:', {
    isAuthenticated: authState.isAuthenticated,
    hasUser: !!authState.user,
    hasToken: !!authState.accessToken,
    expiresAt: authState.expiresAt,
  });

  // Mount components after render
  setTimeout(() => {
    if (authenticated) {
      mountUserMenu();
    }
    mountChatBox();
  }, 0);

  if (authenticated) {
    return `
      <div class="container">
        ${userMenu()}
        <h1>Web App</h1>
        <p>Welcome to your web application.</p>
        ${chatBox()}
      </div>
    `;
  }

  return `
    <div class="container">
      <h1>Web App</h1>
      <p>Welcome to your web application.</p>
      <a href="/login" data-link class="btn btn-primary">Sign in</a>
      ${chatBox()}
    </div>
  `;
}
