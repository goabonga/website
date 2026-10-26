Feature: OAuth2 authentication flow
  As a user
  I want to log in, receive tokens via OAuth2 callback, refresh tokens, and log out
  So that I can securely access the admin interface

  # NOTE: Auth routes do NOT use the standard auth mocking.
  # They ARE the auth flow and require httpx mocking instead.

  # ==========================================================================
  # Login
  # ==========================================================================

  @auth
  Scenario: Login redirects to OAuth2 authorize URL
    When I send a GET request to "/auth/login"
    Then the response status code should be 302
    And I should be redirected to a URL containing "oauth2/authorize"
    And I should be redirected to a URL containing "client_id="
    And I should be redirected to a URL containing "code_challenge="
    And the response should set cookie "oauth_state"
    And the response should set cookie "oauth_code_verifier"

  @auth
  Scenario: Login preserves redirect parameter
    When I send a GET request to "/auth/login?redirect=/billing"
    Then the response status code should be 302
    And I should be redirected to a URL containing "oauth2/authorize"
    And the response should set cookie "oauth_redirect"

  # ==========================================================================
  # Callback - success
  # ==========================================================================

  @auth
  Scenario: Callback with valid code and state sets cookies and redirects
    Given the OAuth2 token endpoint returns valid tokens
    And the OAuth2 userinfo endpoint returns user data
    When I complete the OAuth2 callback with valid state
    Then the response status code should be 302
    And the response should set cookie "access_token"
    And the response should set cookie "refresh_token"
    And the response should set cookie "user_info"

  # ==========================================================================
  # Callback - error responses from OAuth2 provider
  # ==========================================================================

  @auth
  Scenario: Callback with OAuth2 error shows error page
    When I send an OAuth2 callback with error "access_denied" and description "User denied access"
    Then the response status code should be 200
    And the response should be HTML
    And the response should contain "access_denied"

  @auth
  Scenario: Callback with PKCE error redirects to login
    When I send an OAuth2 callback with error "invalid_grant" and description "pkce code_challenge mismatch"
    Then the response status code should be 302
    And I should be redirected to a URL containing "/auth/login"

  # ==========================================================================
  # Callback - missing or invalid parameters
  # ==========================================================================

  @auth
  Scenario: Callback with missing code shows error
    When I send an OAuth2 callback without code
    Then the response status code should be 200
    And the response should be HTML
    And the response should contain "invalid_request"

  @auth
  Scenario: Callback with state mismatch shows error
    When I send an OAuth2 callback with mismatched state
    Then the response status code should be 200
    And the response should be HTML
    And the response should contain "invalid_state"

  @auth
  Scenario: Callback with expired state cookie redirects to login
    When I send an OAuth2 callback without state cookie
    Then the response status code should be 302
    And I should be redirected to a URL containing "/auth/login"

  @auth
  Scenario: Callback with missing code verifier redirects to login
    When I send an OAuth2 callback without code verifier cookie
    Then the response status code should be 302
    And I should be redirected to a URL containing "/auth/login"

  # ==========================================================================
  # Callback - token exchange failure
  # ==========================================================================

  @auth
  Scenario: Callback with token exchange failure shows error
    Given the OAuth2 token endpoint returns an error
    When I complete the OAuth2 callback with valid state
    Then the response status code should be 200
    And the response should be HTML
    And the response should contain "token_exchange_failed"

  # ==========================================================================
  # Logout
  # ==========================================================================

  @auth
  Scenario: Logout clears cookies and redirects
    When I send a GET request to "/auth/logout"
    Then the response status code should be 302
    And I should be redirected to a URL containing "/auth/login"
    And the response should delete cookie "access_token"
    And the response should delete cookie "refresh_token"

  @auth
  Scenario: Logout with custom redirect
    When I send a GET request to "/auth/logout?redirect=/custom"
    Then the response status code should be 302
    And I should be redirected to a URL containing "/custom"

  # ==========================================================================
  # Refresh
  # ==========================================================================

  @auth
  Scenario: Refresh with valid refresh token redirects with new cookies
    Given the OAuth2 token endpoint returns valid tokens for refresh
    When I send a refresh request with a valid refresh token
    Then the response status code should be 302
    And the response should set cookie "access_token"

  @auth
  Scenario: Refresh without refresh token returns 401
    When I send a GET request to "/auth/refresh"
    Then the response status code should be 401

  @auth
  Scenario: Refresh with failed token refresh redirects to login
    Given the OAuth2 token endpoint rejects the refresh token
    When I send a refresh request with a valid refresh token
    Then the response status code should be 302
    And I should be redirected to a URL containing "/auth/login"
