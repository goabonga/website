/**
 * Minimal client-side SPA router with pattern matching.
 */

export type RouteHandler = (
  params?: Record<string, string>
) => string | HTMLElement | Promise<string | HTMLElement>;

export interface Route {
  path: string;
  handler: RouteHandler;
  protected?: boolean;
}

export interface RouterOptions {
  routes: Route[];
  notFound?: RouteHandler;
  error?: (error: Error) => string | HTMLElement;
  isAuthenticated?: () => boolean;
  onAuthRequired?: () => void;
}

class Router {
  private routes: Map<string, { handler: RouteHandler; protected: boolean }> =
    new Map();
  private notFoundHandler: RouteHandler;
  private errorHandler: (error: Error) => string | HTMLElement;
  private isAuthenticated: () => boolean;
  private onAuthRequired: () => void;
  private container: HTMLElement | null = null;

  constructor(options: RouterOptions) {
    for (const route of options.routes) {
      this.routes.set(route.path, {
        handler: route.handler,
        protected: route.protected ?? false,
      });
    }

    this.notFoundHandler = options.notFound ?? (() => this.defaultNotFound());
    this.errorHandler = options.error ?? ((err) => this.defaultError(err));
    this.isAuthenticated = options.isAuthenticated ?? (() => false);
    this.onAuthRequired = options.onAuthRequired ?? (() => this.navigate('/login'));

    window.addEventListener('popstate', () => this.handleRoute());
    document.addEventListener('click', (e) => this.handleClick(e));
  }

  private defaultNotFound(): string {
    return `
      <div class="error-page">
        <div class="error-code">404</div>
        <h1>Page Not Found</h1>
        <p>The page you're looking for doesn't exist.</p>
        <a href="/" data-link>Back to Home</a>
      </div>
    `;
  }

  private defaultError(error: Error): string {
    return `
      <div class="error-page">
        <div class="error-code">500</div>
        <h1>Something Went Wrong</h1>
        <p>${this.escapeHtml(error.message)}</p>
        <a href="/" data-link>Back to Home</a>
      </div>
    `;
  }

  private escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  private handleClick(e: MouseEvent): void {
    const target = e.target as HTMLElement;
    const link = target.closest('a[data-link]') as HTMLAnchorElement | null;

    if (link) {
      e.preventDefault();
      const href = link.getAttribute('href');
      if (href) {
        this.navigate(href);
      }
    }
  }

  public navigate(path: string): void {
    window.history.pushState(null, '', path);
    this.handleRoute();
  }

  public mount(container: HTMLElement): void {
    this.container = container;
    this.handleRoute();
  }

  private async handleRoute(): Promise<void> {
    if (!this.container) return;

    const path = window.location.pathname;
    const match = this.matchRoute(path);

    // Check auth for protected routes
    if (match.protected && !this.isAuthenticated()) {
      this.onAuthRequired();
      return;
    }

    try {
      const content = await match.handler(match.params);
      this.render(content);
    } catch (error) {
      const errorContent = this.errorHandler(error as Error);
      this.render(errorContent);
    }
  }

  private matchRoute(path: string): {
    handler: RouteHandler;
    params?: Record<string, string>;
    protected: boolean;
  } {
    // Exact match first
    if (this.routes.has(path)) {
      const route = this.routes.get(path)!;
      return { handler: route.handler, protected: route.protected };
    }

    // Pattern matching with params (e.g., /users/:id)
    for (const [routePath, route] of this.routes) {
      const params = this.matchPattern(routePath, path);
      if (params) {
        return { handler: route.handler, params, protected: route.protected };
      }
    }

    return { handler: this.notFoundHandler, protected: false };
  }

  private matchPattern(
    pattern: string,
    path: string
  ): Record<string, string> | null {
    const patternParts = pattern.split('/');
    const pathParts = path.split('/');

    if (patternParts.length !== pathParts.length) {
      return null;
    }

    const params: Record<string, string> = {};

    for (let i = 0; i < patternParts.length; i++) {
      const patternPart = patternParts[i];
      const pathPart = pathParts[i];

      if (patternPart.startsWith(':')) {
        params[patternPart.slice(1)] = pathPart;
      } else if (patternPart !== pathPart) {
        return null;
      }
    }

    return params;
  }

  private render(content: string | HTMLElement): void {
    if (!this.container) return;

    if (typeof content === 'string') {
      this.container.innerHTML = content;
    } else {
      this.container.innerHTML = '';
      this.container.appendChild(content);
    }
  }
}

export function createRouter(options: RouterOptions): Router {
  return new Router(options);
}

export default Router;
