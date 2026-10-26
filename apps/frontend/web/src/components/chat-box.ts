/**
 * Chat box component with SSE streaming.
 */

import { fetchSSE } from '../api';
import { getAccessToken } from '../auth';
import { config } from '../config';

interface HistoryResponse {
  messages?: Array<{ role: string; content: string }>;
}

// Chat state
type ChatState = 'idle' | 'loading' | 'streaming' | 'error';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

// Store messages in memory
const messages: ChatMessage[] = [];
let currentState: ChatState = 'idle';
let currentAssistantMessage = '';
let historyLoaded = false;

/**
 * Render chat box component.
 * Call mountChatBox() after rendering to attach event listeners.
 */
export function chatBox(): string {
  return `
    <div id="chat-box" class="chat-box">
      <div id="chat-messages" class="chat-messages">
        ${renderMessages()}
      </div>
      <div class="chat-input-container">
        <textarea
          id="chat-input"
          class="chat-input"
          placeholder="Type a message..."
          rows="1"
        ></textarea>
        <button id="chat-send" class="chat-send-btn btn btn-primary">Send</button>
      </div>
    </div>
  `;
}

/**
 * Render all messages.
 */
function renderMessages(): string {
  if (messages.length === 0) {
    return '<p class="chat-empty">Start a conversation...</p>';
  }

  return messages
    .map(
      (msg, index) => `
      <div class="chat-message chat-message-${msg.role}">
        <div class="chat-message-content" id="msg-content-${index}">${
          msg.role === 'assistant' ? parseMarkdown(msg.content) : escapeHtml(msg.content)
        }</div>
      </div>
    `
    )
    .join('');
}

/**
 * Escape HTML to prevent XSS.
 */
function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Parse markdown to HTML (lightweight parser).
 * Supports: **bold**, *italic*, `inline code`, ```code blocks```, lists, headers.
 */
function parseMarkdown(text: string): string {
  // First escape HTML to prevent XSS
  let html = escapeHtml(text);

  // Code blocks (```...```) - must be processed first
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_match, _lang, code) => {
    return `<pre><code>${code.trim()}</code></pre>`;
  });

  // Inline code (`...`)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Images (![alt](url))
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_match, alt, src) => {
    const safeSrc = src.replace(/&amp;/g, '&');
    return `<img src="${safeSrc}" alt="${alt}" loading="lazy">`;
  });

  // Bold (**...**)
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

  // Italic (*...*)
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // Headers (# ... ##)
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');

  // Unordered lists (- item or * item)
  html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
  // Wrap consecutive <li> in <ul>
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`);

  // Numbered lists (1. item)
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // Wrap consecutive numbered <li> in <ol> (after ul processing)
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => {
    // Only wrap if not already wrapped
    if (!match.startsWith('<ul>') && !match.startsWith('<ol>')) {
      return `<ol>${match}</ol>`;
    }
    return match;
  });

  // Line breaks (preserve single newlines as <br>, except in blocks)
  html = html.replace(/\n/g, '<br>');
  // Clean up extra <br> after block elements
  html = html.replace(/<\/(pre|ul|ol|h[234])><br>/g, '</$1>');
  html = html.replace(/<br><(pre|ul|ol|h[234])>/g, '<$1>');

  return html;
}

/**
 * Update the messages display (full re-render).
 */
function updateMessagesDisplay(): void {
  const container = document.getElementById('chat-messages');
  if (!container) return;

  container.innerHTML = renderMessages();
  scrollToBottom();
}

/**
 * Update only the last message content (for streaming).
 */
function updateLastMessageContent(content: string): void {
  const lastIndex = messages.length - 1;
  const contentEl = document.getElementById(`msg-content-${lastIndex}`);
  if (contentEl) {
    // Use innerHTML with markdown parsing for assistant messages
    contentEl.innerHTML = parseMarkdown(content);
    scrollToBottom();
  }
}

/**
 * Scroll chat to bottom.
 */
function scrollToBottom(): void {
  const container = document.getElementById('chat-messages');
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

/**
 * Update chat state and UI.
 */
function setState(state: ChatState): void {
  currentState = state;
  const chatBox = document.getElementById('chat-box');
  const sendBtn = document.getElementById('chat-send') as HTMLButtonElement;
  const input = document.getElementById('chat-input') as HTMLTextAreaElement;

  if (chatBox) {
    chatBox.className = `chat-box chat-${state}`;
  }

  if (sendBtn) {
    sendBtn.disabled = state === 'loading' || state === 'streaming';
  }

  if (input) {
    input.disabled = state === 'loading' || state === 'streaming';
  }
}

/**
 * Send a message to the chat API.
 */
async function sendMessage(message: string): Promise<void> {
  if (!message.trim() || currentState === 'loading' || currentState === 'streaming') {
    return;
  }

  // Add user message
  messages.push({ role: 'user', content: message.trim() });
  updateMessagesDisplay();

  // Clear input
  const input = document.getElementById('chat-input') as HTMLTextAreaElement;
  if (input) {
    input.value = '';
  }

  // Start loading
  setState('loading');
  currentAssistantMessage = '';

  // Add empty assistant message for streaming
  messages.push({ role: 'assistant', content: '' });

  await fetchSSE(
    '/api/v1/chat',
    { message: message.trim() },
    {
      onHistory: (historyMessages) => {
        if (!historyLoaded) {
          // Load history only once on first response
          // Remove the user message we just added (it's in history)
          messages.length = 0;
          // Add all history messages
          for (const msg of historyMessages) {
            messages.push({ role: msg.role, content: msg.content });
          }
          historyLoaded = true;
          // Add empty assistant message for streaming
          messages.push({ role: 'assistant', content: '' });
          updateMessagesDisplay();
        }
      },
      onMessage: (data) => {
        if (currentState === 'loading') {
          setState('streaming');
          // First token: do a full render to create the message element
          updateMessagesDisplay();
        }
        currentAssistantMessage += data;
        // Update last message content directly (no full re-render)
        messages[messages.length - 1].content = currentAssistantMessage;
        updateLastMessageContent(currentAssistantMessage);
      },
      onError: (error) => {
        console.error('[Chat] Error:', error);
        // Update last message with error
        messages[messages.length - 1].content = `Error: ${error.message}`;
        setState('error');
        updateMessagesDisplay();
      },
      onComplete: () => {
        setState('idle');
      },
    }
  );
}

/**
 * Load conversation history from API.
 */
async function loadHistory(): Promise<void> {
  if (historyLoaded) return;

  try {
    const headers: HeadersInit = { 'Content-Type': 'application/json' };
    const token = getAccessToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${config.apiUrl}/api/v1/chat?history=true`, {
      method: 'POST',
      headers,
      credentials: 'include',
      body: JSON.stringify({ message: '' }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data: HistoryResponse = await response.json();

    if (data.messages) {
      messages.length = 0;
      for (const msg of data.messages) {
        messages.push({
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
        });
      }
      historyLoaded = true;
      updateMessagesDisplay();
    }
  } catch (error) {
    console.error('[Chat] Failed to load history:', error);
  }
}

/**
 * Mount chat box event listeners.
 * Call this after the component is rendered to the DOM.
 */
export function mountChatBox(): void {
  const sendBtn = document.getElementById('chat-send');
  const input = document.getElementById('chat-input') as HTMLTextAreaElement;

  if (sendBtn && input) {
    // Load history on mount
    loadHistory();

    // Send on button click
    sendBtn.addEventListener('click', () => {
      sendMessage(input.value);
    });

    // Send on Enter (without Shift)
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(input.value);
      }
    });

    // Auto-resize textarea
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
    });
  }
}
