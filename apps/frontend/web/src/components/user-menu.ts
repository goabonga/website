/**
 * User menu component - displays user info and logout button.
 */

import { getUser, logout } from '../auth';

/**
 * Generate initials from user name or email.
 */
function getInitials(name?: string, email?: string): string {
  if (name) {
    const parts = name.split(' ');
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
  }
  if (email) {
    return email.substring(0, 2).toUpperCase();
  }
  return 'U';
}

/**
 * Render user menu component.
 * Call mountUserMenu() after rendering to attach event listeners.
 */
export function userMenu(): string {
  const user = getUser();

  if (!user) {
    return '';
  }

  const displayName = user.name || user.email || 'User';
  const initials = getInitials(user.name, user.email);

  return `
    <div class="user-menu">
      <div class="user-avatar">${initials}</div>
      <span class="user-name">${displayName}</span>
      <button id="user-menu-logout" class="btn btn-sm">Sign out</button>
    </div>
  `;
}

/**
 * Mount user menu event listeners.
 * Call this after the component is rendered to the DOM.
 */
export function mountUserMenu(): void {
  const logoutBtn = document.getElementById('user-menu-logout');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => logout());
  }
}
