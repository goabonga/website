/**
 * Login page - redirects to auth server.
 */

import { login } from '../auth';

export function loginPage(): string {
  // Redirect immediately to auth server
  login();

  return `
    <div class="container auth-page">
      <div class="spinner"></div>
      <p>Redirecting to login...</p>
    </div>
  `;
}
