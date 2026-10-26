/**
 * Error page components.
 */

function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

export function notFoundPage(): string {
  return `
    <div class="error-page">
      <div class="error-code">404</div>
      <h1>Page Not Found</h1>
      <p>The page you're looking for doesn't exist.</p>
      <a href="/" data-link class="btn">Back to Home</a>
    </div>
  `;
}

export function errorPage(error: Error): string {
  return `
    <div class="error-page">
      <div class="error-code">500</div>
      <h1>Something Went Wrong</h1>
      <p>${escapeHtml(error.message)}</p>
      <a href="/" data-link class="btn">Back to Home</a>
    </div>
  `;
}

export function forbiddenPage(): string {
  return `
    <div class="error-page">
      <div class="error-code">403</div>
      <h1>Access Denied</h1>
      <p>You don't have permission to access this page.</p>
      <a href="/" data-link class="btn">Back to Home</a>
    </div>
  `;
}

export function unauthorizedPage(): string {
  return `
    <div class="error-page">
      <div class="error-code">401</div>
      <h1>Authentication Required</h1>
      <p>Please sign in to access this page.</p>
      <a href="/login" data-link class="btn btn-primary">Sign in</a>
    </div>
  `;
}
