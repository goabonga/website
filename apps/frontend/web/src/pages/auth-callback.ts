/**
 * Auth callback page component.
 */

import { handleCallback, scheduleTokenRefresh } from '../auth';

export async function authCallbackPage(): Promise<string> {
  console.log('[Callback] Auth callback page loaded');

  try {
    const returnTo = await handleCallback();

    console.log('[Callback] handleCallback completed, redirecting to:', returnTo);

    // Schedule automatic token refresh
    scheduleTokenRefresh();

    // Delay redirect to show success message
    setTimeout(() => {
      window.location.href = returnTo;
    }, 2000);

    return `
      <section id="auth-callback">
        <main>
          <p>Authentication successful. Redirecting...</p>
        </main>
      </section>
    `;
  } catch (error) {
    console.error('[Callback] Error during auth callback:', error);
    const message = error instanceof Error ? error.message : 'Authentication failed';

    // Attach click handler after render
    setTimeout(() => {
      const retryBtn = document.getElementById('retry-btn');
      if (retryBtn) {
        retryBtn.addEventListener('click', () => {
          window.location.href = '/login';
        });
      }
    }, 0);

    return `
      <section id="auth-callback">
        <main>
          <h1>Error</h1>
          <p>${message}</p>
          <p><button id="retry-btn" class="btn">Try Again</button></p>
        </main>
      </section>
    `;
  }
}
