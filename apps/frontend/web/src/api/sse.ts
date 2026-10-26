/**
 * SSE (Server-Sent Events) streaming service.
 */

import { getAccessToken, login, logout } from '../auth';
import { getAnalytics } from '../analytics';
import { config } from '../config';

export interface ChatHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ClientAction {
  client_action: 'auth_login' | 'auth_logout' | 'open_url' | 'display_image' | 'none';
  url?: string;
  image_url?: string;
  image_alt?: string;
}

export interface ToolResult {
  data?: ClientAction;
}

export interface SSEOptions {
  onMessage: (data: string) => void;
  onHistory?: (messages: ChatHistoryMessage[]) => void;
  onError?: (error: Error) => void;
  onComplete?: () => void;
}

// Track if a navigation action is pending (to suppress stream errors)
let navigationPending = false;

/**
 * Check if navigation is pending (stream errors should be ignored).
 */
export function isNavigationPending(): boolean {
  return navigationPending;
}

/**
 * Handle client actions from tool results.
 * Uses auth.ts functions for authentication flows.
 */
function handleClientAction(action: ClientAction, onMessage?: (data: string) => void): void {
  // Track tool action
  getAnalytics()?.track('tool_executed', {
    action: action.client_action,
    has_url: !!action.url,
  });

  switch (action.client_action) {
    case 'auth_login':
      navigationPending = true;
      getAnalytics()?.track('tool_auth_login');
      login();
      break;
    case 'auth_logout':
      navigationPending = true;
      getAnalytics()?.track('tool_auth_logout');
      logout();
      break;
    case 'open_url':
      if (action.url) {
        getAnalytics()?.track('tool_open_url', { url: action.url });
        window.open(action.url, '_blank');
      }
      break;
    case 'display_image':
      if (action.image_url && onMessage) {
        const alt = action.image_alt || '';
        getAnalytics()?.track('tool_display_image', { image_url: action.image_url });
        onMessage(`\n\n![${alt}](${action.image_url})\n\n`);
      }
      break;
    case 'none':
      // No action needed
      break;
  }
}

/**
 * Fetch with SSE streaming response.
 * Handles credentials for httpOnly cookies and optional Bearer token.
 */
export async function fetchSSE(
  endpoint: string,
  body: Record<string, unknown>,
  options: SSEOptions
): Promise<void> {
  const { onMessage, onError, onComplete } = options;

  const url = `${config.apiUrl}${endpoint}`;
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  // Add Bearer token if authenticated (optional auth)
  const token = getAccessToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers,
      credentials: 'include', // Send httpOnly cookies
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      // Handle revoked/invalid token - auto logout on 401
      if (response.status === 401) {
        console.warn('[SSE] Token revoked or invalid, logging out');
        navigationPending = true;
        logout();
        return;
      }
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    if (!response.body) {
      throw new Error('No response body');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      // Process complete SSE events (separated by double newline)
      const events = buffer.split('\n\n');
      buffer = events.pop() || ''; // Keep incomplete event in buffer

      for (const event of events) {
        const lines = event.split('\n');
        let eventType = '';
        let eventData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            eventData = line.slice(6);
          }
        }

        // Handle different event types
        if (eventType === 'token' && eventData) {
          try {
            const parsed = JSON.parse(eventData);
            if (parsed.content) {
              onMessage(parsed.content);
            }
          } catch {
            // If not JSON, pass as-is
            onMessage(eventData);
          }
        } else if (eventType === 'history' && eventData && options.onHistory) {
          try {
            const parsed = JSON.parse(eventData);
            if (Array.isArray(parsed.messages)) {
              options.onHistory(parsed.messages);
            }
          } catch {
            console.error('[SSE] Failed to parse history event');
          }
        } else if (eventType === 'tools' && eventData) {
          try {
            const parsed = JSON.parse(eventData);
            // Track tools event received
            getAnalytics()?.track('tools_received', {
              tool_count: Array.isArray(parsed.results) ? parsed.results.length : 0,
            });
            // Check for client actions in tool results
            if (Array.isArray(parsed.results)) {
              for (const result of parsed.results as ToolResult[]) {
                if (result.data?.client_action) {
                  handleClientAction(result.data, onMessage);
                }
              }
            }
          } catch {
            console.error('[SSE] Failed to parse tools event');
          }
        }
        // Ignore other event types: intent, rag, done, error
      }
    }

    // Process any remaining event in buffer
    if (buffer.trim()) {
      const lines = buffer.split('\n');
      let eventType = '';
      let eventData = '';

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          eventData = line.slice(6);
        }
      }

      if (eventType === 'token' && eventData) {
        try {
          const parsed = JSON.parse(eventData);
          if (parsed.content) {
            onMessage(parsed.content);
          }
        } catch {
          onMessage(eventData);
        }
      }
    }

    onComplete?.();
  } catch (error) {
    // Ignore stream errors when navigation is pending (login/logout redirect)
    if (navigationPending) {
      return;
    }
    const err = error instanceof Error ? error : new Error(String(error));
    console.error('[SSE] Error:', err.message);
    onError?.(err);
  }
}
