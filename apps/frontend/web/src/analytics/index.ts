/**
 * Analytics SDK for event collection.
 * Sends events to the analytics service (ua.goabonga.com).
 */

export interface AnalyticsEvent {
  event_type: string;
  page_url?: string;
  page_title?: string;
  event_data?: Record<string, unknown>;
}

export interface AnalyticsConfig {
  endpoint: string;
  userId?: string;
  debug?: boolean;
}

class Analytics {
  private config: AnalyticsConfig;
  private queue: AnalyticsEvent[] = [];
  private flushTimeout: ReturnType<typeof setTimeout> | null = null;
  private readonly FLUSH_INTERVAL = 5000; // 5 seconds
  private readonly MAX_QUEUE_SIZE = 10;

  constructor(config: AnalyticsConfig) {
    this.config = config;

    // Flush queue on page unload
    window.addEventListener('beforeunload', () => this.flush());
    window.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') {
        this.flush();
      }
    });

    // Auto-track page views on navigation
    this.setupAutoTracking();
  }

  /**
   * Set the user ID for authenticated users.
   */
  setUserId(userId: string | undefined): void {
    this.config.userId = userId;
  }

  /**
   * Track a custom event.
   */
  track(eventType: string, eventData?: Record<string, unknown>): void {
    const event: AnalyticsEvent = {
      event_type: eventType,
      page_url: window.location.pathname,
      page_title: document.title,
    };

    if (eventData) {
      event.event_data = eventData;
    }

    this.enqueue(event);
  }

  /**
   * Track a page view.
   */
  pageView(url?: string, title?: string): void {
    const event: AnalyticsEvent = {
      event_type: 'pageview',
      page_url: url || window.location.pathname,
      page_title: title || document.title,
    };

    this.enqueue(event);
  }

  /**
   * Track a click event.
   */
  click(element: string, data?: Record<string, unknown>): void {
    this.track('click', { element, ...data });
  }

  private enqueue(event: AnalyticsEvent): void {
    this.queue.push(event);

    if (this.config.debug) {
      console.log('[Analytics] Event queued:', event);
    }

    // Flush immediately if queue is full
    if (this.queue.length >= this.MAX_QUEUE_SIZE) {
      this.flush();
    } else {
      // Schedule flush
      this.scheduleFlush();
    }
  }

  private scheduleFlush(): void {
    if (this.flushTimeout) return;

    this.flushTimeout = setTimeout(() => {
      this.flush();
    }, this.FLUSH_INTERVAL);
  }

  /**
   * Send all queued events to the analytics server.
   */
  async flush(): Promise<void> {
    if (this.flushTimeout) {
      clearTimeout(this.flushTimeout);
      this.flushTimeout = null;
    }

    if (this.queue.length === 0) return;

    const events = [...this.queue];
    this.queue = [];

    const payload: { events: AnalyticsEvent[]; user_id?: string } = { events };
    if (this.config.userId) {
      payload.user_id = this.config.userId;
    }

    try {
      // Use sendBeacon for reliability on page unload
      if (navigator.sendBeacon && document.visibilityState === 'hidden') {
        const blob = new Blob([JSON.stringify(payload)], {
          type: 'application/json',
        });
        const sent = navigator.sendBeacon(this.config.endpoint, blob);

        if (this.config.debug) {
          console.log('[Analytics] Beacon sent:', sent, events);
        }
      } else {
        // Use fetch for normal operation
        const response = await fetch(this.config.endpoint, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        if (this.config.debug) {
          console.log('[Analytics] Events sent:', response.ok, events);
        }

        if (!response.ok) {
          // Re-queue events on failure
          this.queue.unshift(...events);
        }
      }
    } catch (error) {
      if (this.config.debug) {
        console.error('[Analytics] Failed to send events:', error);
      }
      // Re-queue events on failure
      this.queue.unshift(...events);
    }
  }

  private setupAutoTracking(): void {
    // Track initial page view
    this.pageView();

    // Track SPA navigation using History API
    const originalPushState = history.pushState.bind(history);
    const originalReplaceState = history.replaceState.bind(history);

    history.pushState = (...args) => {
      originalPushState(...args);
      this.pageView();
    };

    history.replaceState = (...args) => {
      originalReplaceState(...args);
      this.pageView();
    };

    window.addEventListener('popstate', () => {
      this.pageView();
    });
  }
}

let analyticsInstance: Analytics | null = null;

/**
 * Initialize the analytics SDK.
 */
export function initAnalytics(config: AnalyticsConfig): Analytics {
  if (analyticsInstance) {
    return analyticsInstance;
  }

  analyticsInstance = new Analytics(config);
  return analyticsInstance;
}

/**
 * Get the analytics instance.
 */
export function getAnalytics(): Analytics | null {
  return analyticsInstance;
}

export default Analytics;
