import './style.css';
import { config } from './config';
import { fetchSSE, type ChatHistoryMessage } from './api';
import { getAccessToken, isAuthenticated, login, logout, scheduleTokenRefresh, getUser } from './auth';
import { createRouter } from './router';
import { authCallbackPage } from './pages/auth-callback';
import { initAnalytics, getAnalytics } from './analytics';

// Log config in development
if (import.meta.env.DEV) {
  console.log('App config:', config);
}

/**
 * Add auth links (Settings, Logout) to navigation if user is authenticated.
 */
function addAuthLinksToNav(nav: Element): void {
  if (!isAuthenticated()) return;

  // Create auth links container
  const authLinksContainer = document.createElement('div');
  authLinksContainer.className = 'nav-auth-links';

  // Settings link
  const settingsLink = document.createElement('a');
  settingsLink.href = `${config.authUrl}/auth/settings`;
  settingsLink.textContent = 'Settings';
  settingsLink.target = '_blank';
  settingsLink.rel = 'noopener noreferrer';
  authLinksContainer.appendChild(settingsLink);

  // Logout link
  const logoutLink = document.createElement('a');
  logoutLink.href = '#';
  logoutLink.textContent = 'Logout';
  logoutLink.addEventListener('click', (e) => {
    e.preventDefault();
    logout();
  });
  authLinksContainer.appendChild(logoutLink);

  nav.appendChild(authLinksContainer);
}

/**
 * Initialize the burger menu
 */
function initBurgerMenu(): void {
  const nav = document.querySelector('nav[role=navigation]');
  const body = document.body;

  if (!nav) return;

  // Add auth links if authenticated
  addAuthLinksToNav(nav);

  // Create burger button dynamically
  const button = document.createElement('button');
  button.classList.add('burger');
  button.innerHTML = 'MENU';
  nav.parentNode?.insertBefore(button, nav);

  const isPoliciesOpen = () => {
    const policiesSection = document.querySelector('.policies');
    return policiesSection && !policiesSection.classList.contains('unvisible');
  };

  const updateButtonText = () => {
    if (isPoliciesOpen() || body.classList.contains('active')) {
      button.innerHTML = 'CLOSE';
    } else {
      button.innerHTML = 'MENU';
    }
  };

  button.addEventListener('click', () => {
    // Don't toggle menu if policies is open (handled by initPoliciesToggle)
    if (isPoliciesOpen()) return;

    if (body.classList.contains('active')) {
      body.classList.remove('active');
    } else {
      body.classList.add('active');
    }
    updateButtonText();
  });

  // Close menu when clicking a nav link
  const navLinks = nav.querySelectorAll('a');
  navLinks.forEach((link) => {
    link.addEventListener('click', () => {
      body.classList.remove('active');
      updateButtonText();
    });
  });

  // Close menu on escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && body.classList.contains('active')) {
      body.classList.remove('active');
      updateButtonText();
    }
  });
}

/**
 * Initialize policies section toggle
 */
function initPoliciesToggle(): void {
  let beforePolicies: string | null = null;

  const burgerButton = document.querySelector('.burger');
  const policiesButton = document.querySelector('a[href="#policies"]');
  const policiesSection = document.querySelector('.policies');
  const body = document.body;

  if (!policiesSection || !burgerButton) return;

  // Remove the close button from policies section (burger will handle it)
  const closeButton = policiesSection.querySelector('.close');
  closeButton?.remove();

  const closePolicies = () => {
    policiesSection.classList.add('unvisible');
    body.classList.remove('policies-open');
    if (beforePolicies) {
      window.location.hash = beforePolicies;
    }
    updateBurgerText();
  };

  const openPolicies = () => {
    beforePolicies = window.location.hash;
    policiesSection.classList.remove('unvisible');
    body.classList.add('policies-open');
    updateBurgerText();
  };

  const isPoliciesOpen = () => !policiesSection.classList.contains('unvisible');

  const updateBurgerText = () => {
    if (isPoliciesOpen()) {
      burgerButton.innerHTML = 'CLOSE';
    } else if (body.classList.contains('active')) {
      burgerButton.innerHTML = 'CLOSE';
    } else {
      burgerButton.innerHTML = 'MENU';
    }
  };

  // Handle burger button click for policies
  burgerButton.addEventListener('click', () => {
    if (isPoliciesOpen()) {
      closePolicies();
    }
  });

  policiesButton?.addEventListener('click', (event) => {
    event.preventDefault();
    // Close menu if open before showing policies
    if (body.classList.contains('active')) {
      body.classList.remove('active');
    }
    openPolicies();
  });

  // Close on escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isPoliciesOpen()) {
      closePolicies();
    }
  });
}

/**
 * Animated headline - typing effect with LLM input transition
 */
/**
 * Parse markdown to HTML (lightweight parser).
 * Supports: **bold**, *italic*, `inline code`, ```code blocks```, lists, headers.
 */
function parseMarkdown(text: string): string {
  // Escape HTML to prevent XSS
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

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

  // Unordered lists (- item or * item at start of line)
  html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');

  // Numbered lists (1. item)
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

  // Wrap consecutive <li> in <ul>
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`);

  // Line breaks (preserve single newlines as <br>)
  html = html.replace(/\n/g, '<br>');

  // Clean up extra <br> after block elements
  html = html.replace(/<\/(pre|ul|ol|h[234])><br>/g, '</$1>');
  html = html.replace(/<br><(pre|ul|ol|h[234])>/g, '<$1>');

  return html;
}

class AnimatedHeadline {
  private element: HTMLElement;
  private words: HTMLElement[];
  private currentWordIndex: number = 0;
  private animationDelay: number = 2500;
  private typeLettersDelay: number = 150;
  private selectionDuration: number = 500;
  private chatContainer: HTMLElement | null = null;
  private typeAnimationDelay: number = this.selectionDuration + 800;
  private finalMessage: string = 'What can I do for you?';
  private isStreaming: boolean = false;
  private responseContainer: HTMLElement | null = null;
  private responseText: string = '';
  private lastMessage: string = '';
  private lastContainer: HTMLElement | null = null;
  private static readonly SESSION_KEY = 'llm_intro_shown';

  constructor(element: HTMLElement) {
    this.element = element;
    this.words = Array.from(element.querySelectorAll('.cd-words-wrapper b'));
    this.init();
  }

  private init(): void {
    if (this.words.length === 0) return;

    // Check if intro was already shown in this session
    if (sessionStorage.getItem(AnimatedHeadline.SESSION_KEY)) {
      this.skipToLLMInput();
      return;
    }

    this.singleLetters();
    this.animateHeadline();
  }

  private skipToLLMInput(): void {
    // Find the welcome main element
    const welcomeMain = this.element.closest('#welcome') as HTMLElement;
    const h1Element = welcomeMain?.querySelector('h1');

    // Remove h1 element
    if (h1Element) {
      h1Element.remove();
    }

    // Prepare h2 for llm mode
    this.element.classList.remove('type');
    this.element.classList.remove('letters');
    this.element.classList.add('llm-mode');
    this.element.innerHTML = this.finalMessage;

    // Create container for chat
    this.chatContainer = document.createElement('div');
    this.chatContainer.className = 'llm-chat-container';
    welcomeMain?.appendChild(this.chatContainer);

    // Load history then show input with smooth transition
    this.loadHistory().then(() => {
      this.showInput(this.chatContainer!);
      this.setupGlobalClickHandler();

      // Reveal content after DOM is ready (CSS hides it via html.llm-intro-seen)
      requestAnimationFrame(() => {
        if (welcomeMain) {
          welcomeMain.classList.add('llm-ready');
        }
      });
    });
  }

  private async loadHistory(): Promise<void> {
    if (!this.chatContainer) return;

    try {
      const headers: HeadersInit = { 'Content-Type': 'application/json' };
      const token = getAccessToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      // Use POST /api/v1/chat?history=true as per API spec
      const response = await fetch(`${config.apiUrl}/api/v1/chat?history=true`, {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify({ message: '' }),
      });

      if (!response.ok) {
        if (response.status === 401) {
          // Not authenticated, no history to load
          return;
        }
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      const messages: ChatHistoryMessage[] = data.messages || [];

      // Render history messages
      for (const msg of messages) {
        if (msg.role === 'user') {
          // Create frozen input for user message
          const inputSpan = document.createElement('span');
          inputSpan.className = 'llm-input sent';
          inputSpan.textContent = msg.content;
          this.chatContainer.appendChild(inputSpan);
        } else if (msg.role === 'assistant') {
          // Create response container for assistant message
          const responseSpan = document.createElement('span');
          responseSpan.className = 'llm-response';
          responseSpan.innerHTML = parseMarkdown(msg.content);
          this.chatContainer.appendChild(responseSpan);
        }
      }
    } catch (error) {
      console.error('[LLM] Failed to load history:', error);
    }
  }

  private singleLetters(): void {
    this.words.forEach((word, wordIndex) => {
      const letters = word.textContent?.split('') || [];
      word.innerHTML = '';
      letters.forEach((letter) => {
        const span = document.createElement('i');
        span.textContent = letter;
        if (wordIndex === 0) {
          span.classList.add('in');
        }
        word.appendChild(span);
      });
    });
  }

  private animateHeadline(): void {
    setTimeout(() => {
      this.hideWord(this.words[0]);
    }, this.animationDelay);
  }

  private hideWord(word: HTMLElement): void {
    const wrapper = word.closest('.cd-words-wrapper');

    if (this.element.classList.contains('type')) {
      wrapper?.classList.add('selected');
      setTimeout(() => {
        wrapper?.classList.remove('selected');
        word.classList.remove('is-visible');
        word.classList.add('is-hidden');
        const letters = Array.from(word.querySelectorAll('i'));
        letters.forEach((letter) => letter.classList.remove('in'));
      }, this.selectionDuration);

      setTimeout(() => {
        const nextIndex = this.currentWordIndex + 1;
        if (nextIndex < this.words.length) {
          this.currentWordIndex = nextIndex;
          this.showWord(this.words[nextIndex]);
        }
        // Last word transition is handled in showWord to keep it visible
      }, this.typeAnimationDelay);
    }
  }

  private showWord(word: HTMLElement): void {
    if (this.element.classList.contains('type')) {
      const isLastWord = this.currentWordIndex === this.words.length - 1;
      this.showLetters(Array.from(word.querySelectorAll('i')), () => {
        if (isLastWord) {
          // Last word: keep it visible, then transition to LLM input
          setTimeout(() => this.transitionToLLMInput(), this.animationDelay);
        } else {
          setTimeout(() => this.hideWord(word), this.animationDelay);
        }
      });
      word.classList.add('is-visible');
      word.classList.remove('is-hidden');
    }
  }

  private showLetters(letters: Element[], callback: () => void): void {
    if (letters.length === 0) {
      callback();
      return;
    }
    letters.forEach((letter, index) => {
      setTimeout(() => {
        letter.classList.remove('out');
        letter.classList.add('in');
        if (index === letters.length - 1) {
          callback();
        }
      }, index * this.typeLettersDelay);
    });
  }

  private transitionToLLMInput(): void {
    // Find the welcome main element (which contains h1 and h2)
    const welcomeMain = this.element.closest('#welcome') as HTMLElement;
    const h1Element = welcomeMain?.querySelector('h1');

    // Select the entire welcome section content (h1 + h2)
    if (welcomeMain) {
      welcomeMain.classList.add('selecting-all');
    }

    setTimeout(() => {
      // Remove selection and clear content
      if (welcomeMain) {
        welcomeMain.classList.remove('selecting-all');
      }

      // Remove h1 element
      if (h1Element) {
        h1Element.remove();
      }

      // Clear and prepare h2 for the final message only
      this.element.classList.remove('type');
      this.element.classList.remove('letters');
      this.element.classList.add('llm-mode');
      this.element.innerHTML = '';

      // Create container for chat (inputs/responses) - placed after h2
      this.chatContainer = document.createElement('div');
      this.chatContainer.className = 'llm-chat-container';
      welcomeMain?.appendChild(this.chatContainer);

      // Type the final message in h2
      this.typeMessage(this.element, this.finalMessage, async () => {
        // Mark intro as shown for this session
        sessionStorage.setItem(AnimatedHeadline.SESSION_KEY, 'true');

        // Load history then show input
        await this.loadHistory();
        this.showInput(this.chatContainer!);
        this.setupGlobalClickHandler();
      });
    }, this.selectionDuration);
  }

  private typeMessage(container: HTMLElement, message: string, callback: () => void): void {
    const chars = message.split('');
    let index = 0;

    const typeChar = () => {
      if (index < chars.length) {
        const span = document.createElement('i');
        span.textContent = chars[index];
        span.classList.add('in');
        span.style.fontStyle = 'normal';
        container.appendChild(span);
        index++;
        setTimeout(typeChar, this.typeLettersDelay);
      } else {
        callback();
      }
    };

    typeChar();
  }

  private setupGlobalClickHandler(): void {
    // Focus the active input when clicking anywhere on the page
    document.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      // Don't focus if clicking on nav links, burger menu, or policies
      if (
        !target.closest('nav') &&
        !target.closest('.burger') &&
        !target.closest('.policies') &&
        !target.closest('footer') &&
        this.chatContainer
      ) {
        // Find the last active (editable) input
        const inputs = this.chatContainer.querySelectorAll('.llm-input[contenteditable="true"]');
        const lastInput = inputs[inputs.length - 1] as HTMLElement;
        if (lastInput) {
          lastInput.focus();
        }
      }
    });
  }

  private showInput(container: HTMLElement): void {
    // Create editable span for inline input
    const editableSpan = document.createElement('span');
    editableSpan.className = 'llm-input';
    editableSpan.contentEditable = 'true';
    editableSpan.setAttribute('data-placeholder', 'Type your message...');
    editableSpan.spellcheck = false;

    container.appendChild(editableSpan);

    // Focus the editable span
    setTimeout(() => {
      editableSpan.focus();
    }, 100);

    // Handle input submission
    editableSpan.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const message = editableSpan.textContent?.trim() || '';
        if (message) {
          this.handleUserInput(message, container);
        }
      }
    });

    // Handle placeholder visibility and clean up browser-inserted elements
    editableSpan.addEventListener('input', () => {
      // Remove any <br> tags inserted by browser when content is empty
      if (editableSpan.innerHTML === '<br>' || editableSpan.textContent === '') {
        editableSpan.innerHTML = '';
        editableSpan.classList.remove('has-content');
      } else {
        editableSpan.classList.add('has-content');
      }
    });
  }

  private handleUserInput(message: string, container: HTMLElement): void {
    if (this.isStreaming) return;

    // Track chat message sent
    getAnalytics()?.track('chat_message_sent', {
      message_length: message.length,
    });

    // Dispatch custom event for LLM integration
    const event = new CustomEvent('llm-input', {
      detail: { message },
      bubbles: true,
    });
    this.element.dispatchEvent(event);

    // Send message via SSE and display response
    this.sendToChat(message, container);
  }

  private async sendToChat(message: string, container: HTMLElement): Promise<void> {
    this.isStreaming = true;
    this.lastMessage = message;
    this.lastContainer = container;

    // Get the last input element and freeze it (gray out, remove editable)
    const inputs = container.querySelectorAll('.llm-input');
    const inputEl = inputs[inputs.length - 1] as HTMLElement;
    if (inputEl) {
      inputEl.removeAttribute('contenteditable');
      inputEl.classList.add('sent');
    }

    // Create new response container for this message
    this.responseContainer = document.createElement('span');
    this.responseContainer.className = 'llm-response';
    container.appendChild(this.responseContainer);
    this.responseText = '';

    // Add loading indicator
    this.responseContainer.innerHTML = '<span class="llm-loading">...</span>';

    try {
      await fetchSSE(
        '/api/v1/chat',
        { message },
        {
          onMessage: (token) => {
            // Remove loading indicator on first token
            const loadingEl = this.responseContainer?.querySelector('.llm-loading');
            if (loadingEl) {
              loadingEl.remove();
            }

            // Accumulate text and update with parsed markdown
            this.responseText += token;
            if (this.responseContainer) {
              this.responseContainer.innerHTML = parseMarkdown(this.responseText);
            }
          },
          onError: (error) => {
            console.error('[LLM] Error:', error);
            this.showError(error.message, inputEl);
          },
          onComplete: () => {
            this.isStreaming = false;
            // Final markdown parse
            if (this.responseContainer) {
              this.responseContainer.innerHTML = parseMarkdown(this.responseText);
            }

            // Track chat response received
            getAnalytics()?.track('chat_response_received', {
              response_length: this.responseText.length,
            });

            // Add new input after response
            this.addNewInput(container);
          },
        }
      );
    } catch (error) {
      console.error('[LLM] Error:', error);
      const errorMessage = error instanceof Error ? error.message : String(error);
      this.showError(errorMessage, inputEl);
    }
  }

  private addNewInput(container: HTMLElement): void {
    // Reset response container for next message
    this.responseContainer = null;

    // Create new editable span for next input
    const editableSpan = document.createElement('span');
    editableSpan.className = 'llm-input';
    editableSpan.contentEditable = 'true';
    editableSpan.setAttribute('data-placeholder', 'Type your message...');
    editableSpan.spellcheck = false;

    container.appendChild(editableSpan);

    // Focus the new input and scroll to it
    setTimeout(() => {
      editableSpan.focus();
      editableSpan.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);

    // Handle input submission
    editableSpan.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const message = editableSpan.textContent?.trim() || '';
        if (message) {
          this.handleUserInput(message, container);
        }
      }
    });

    // Handle placeholder visibility and clean up browser-inserted elements
    editableSpan.addEventListener('input', () => {
      // Remove any <br> tags inserted by browser when content is empty
      if (editableSpan.innerHTML === '<br>' || editableSpan.textContent === '') {
        editableSpan.innerHTML = '';
        editableSpan.classList.remove('has-content');
      } else {
        editableSpan.classList.add('has-content');
      }
    });
  }

  private showError(errorMessage: string, _inputEl: HTMLElement | null): void {
    this.isStreaming = false;

    // Track chat error
    getAnalytics()?.track('chat_error', {
      error_message: errorMessage,
    });

    if (this.responseContainer) {
      this.responseContainer.classList.add('has-error');
      this.responseContainer.innerHTML = `
        <span class="llm-error">Error: ${errorMessage}</span>
        <button class="llm-retry" type="button">Retry</button>
      `;

      // Add retry click handler
      const retryBtn = this.responseContainer.querySelector('.llm-retry');
      retryBtn?.addEventListener('click', () => {
        // Track retry click
        getAnalytics()?.track('chat_retry');

        if (this.lastMessage && this.lastContainer) {
          this.sendToChat(this.lastMessage, this.lastContainer);
        }
      });
    }
  }
}

/**
 * Initialize all animated headlines
 */
function initAnimatedHeadlines(): void {
  const headlines = document.querySelectorAll<HTMLElement>('.cd-headline');
  headlines.forEach((headline) => new AnimatedHeadline(headline));
}

/**
 * Initialize the router for SPA navigation.
 */
function initRouter(): void {
  const appContainer = document.getElementById('app');
  if (!appContainer) return;

  const router = createRouter({
    routes: [
      {
        path: '/auth/callback',
        handler: authCallbackPage,
      },
    ],
    isAuthenticated,
    onAuthRequired: () => login(window.location.pathname),
  });

  router.mount(appContainer);
}

/**
 * Initialize analytics tracking.
 */
function initAnalyticsTracking(): void {
  if (!config.analyticsUrl) {
    if (import.meta.env.DEV) {
      console.warn('[Analytics] No analytics URL configured, skipping');
    }
    return;
  }

  const analytics = initAnalytics({
    endpoint: `${config.analyticsUrl}/collect`,
    debug: import.meta.env.DEV,
  });

  // Set user ID if authenticated
  if (isAuthenticated()) {
    const user = getUser();
    if (user?.sub) {
      analytics.setUserId(user.sub);
    }
  }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  // Note: 'js' class is already added by inline script in <head> to prevent FOUC

  // Check if we're on a route that needs the router
  const pathname = window.location.pathname;
  if (pathname === '/auth/callback') {
    initRouter();
    return;
  }

  // Initialize analytics tracking
  initAnalyticsTracking();

  // Schedule automatic token refresh if user is authenticated
  if (isAuthenticated()) {
    scheduleTokenRefresh();
  }

  // Normal page initialization
  initBurgerMenu();
  initPoliciesToggle();
  initAnimatedHeadlines();
});
