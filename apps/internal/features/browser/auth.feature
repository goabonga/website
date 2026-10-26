@browser
Feature: OAuth2 login in a browser
  As an operator
  I want to sign in through the identity provider and sign out again
  So that only authenticated users reach the dashboard

  # The application is served on a real socket and the provider is the fake OpenID
  # provider of e2e_support: the authorization code flow with PKCE, the userinfo call
  # and the cookies are the real ones.

  Background:
    Given a user holding the scopes "*" exists at the provider

  # --- Signing in ---

  Scenario: Signing in goes through the provider and comes back to the page asked for
    When I navigate to "/auth/login?redirect=/health"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/health"
    And I should see "healthy"
    And the provider should have received a "authorization_code" token request

  Scenario: The login sets the session cookies and clears the temporary ones
    When I navigate to "/auth/login"
    And I sign in at the provider
    Then the cookie "access_token" should be set
    And the cookie "refresh_token" should be set
    And the cookie "user_info" should be set
    And the cookie "oauth_state" should not be set
    And the cookie "oauth_redirect" should not be set
    And the cookie "oauth_code_verifier" should not be set

  Scenario: The token cookies are not readable by scripts
    When I navigate to "/auth/login"
    And I sign in at the provider
    Then the cookie "access_token" should be http only
    And the cookie "refresh_token" should be http only
    And the cookie "access_token" should have the SameSite policy "Lax"
    And the cookie "user_info" should be readable by scripts

  Scenario: The login cookies are set while the browser is at the provider
    When I navigate to "/auth/login"
    Then I should be asked to sign in at the provider
    And the cookie "oauth_state" should be http only
    And the cookie "oauth_code_verifier" should be http only
    And the cookie "access_token" should not be set

  Scenario: A wrong password keeps the user at the provider
    When I navigate to "/auth/login"
    And I sign in at the provider as the user "unknown@example.test" with the password "wrong"
    Then I should see "Invalid email or password."
    And I should be asked to sign in at the provider
    And the cookie "access_token" should not be set
    And the provider should have received no token request

  Scenario: A user who denies the consent is told so
    Given the provider asks users for their consent
    When I navigate to "/auth/login"
    And I sign in at the provider
    And I click "Deny"
    Then I should see "Authentication Error"
    And I should see "access_denied"
    And the cookie "access_token" should not be set

  Scenario: A user who allows the consent is signed in
    Given the provider asks users for their consent
    When I navigate to "/auth/login?redirect=/health"
    And I sign in at the provider
    And I click "Allow"
    Then the URL should be "/health"
    And the cookie "access_token" should be set

  # --- The callback ---

  Scenario: The callback shows the error the provider reports and offers to try again
    When I navigate to "/auth/callback?error=access_denied&error_description=You+said+no"
    Then I should see "Authentication Error"
    And I should see "access_denied"
    And I should see "You said no"
    When I click "Try Again"
    Then I should be asked to sign in at the provider

  Scenario: The callback without a code is an invalid request
    When I navigate to "/auth/callback"
    Then I should see "invalid_request"
    And I should see "Missing authorization code or state parameter."

  Scenario: The callback refuses a state that is not the one of the login
    When I navigate to "/auth/login"
    And I navigate to "/auth/callback?code=some-code&state=forged"
    Then I should see "invalid_state"
    And the cookie "access_token" should not be set

  Scenario: The callback sends a user whose login expired back to the provider
    When I navigate to "/auth/callback?code=some-code&state=some-state"
    Then I should be asked to sign in at the provider

  Scenario: The callback reports an authorization code the provider refuses
    When I navigate to "/auth/login"
    And I return to the callback with the code "forged-code" and the state of my login
    Then I should see "token_exchange_failed"
    And the cookie "access_token" should not be set

  # --- Refreshing the token ---

  Scenario: Refreshing the token rotates the cookies
    Given I sign in as a super administrator
    And I remember the value of the cookie "access_token"
    And I remember the value of the cookie "refresh_token"
    When I navigate to "/auth/refresh"
    Then the cookie "access_token" should differ from the remembered value
    And the cookie "refresh_token" should differ from the remembered value
    And the provider should have received a "refresh_token" token request

  Scenario: Refreshing without a session is refused
    When I navigate to "/auth/refresh"
    Then I should see "No refresh token"

  Scenario: A refresh token the provider no longer knows sends the user to log in again
    Given I sign in as a super administrator
    And the provider revokes every token
    And the provider ends every session
    When I navigate to "/auth/refresh"
    Then I should be asked to sign in at the provider
    And the cookie "access_token" should not be set

  # --- Signing out ---

  Scenario: Signing out clears the session cookies
    Given I sign in as a super administrator
    When I sign out
    Then the URL should be "/health"
    And the cookie "access_token" should not be set
    And the cookie "refresh_token" should not be set
    And the cookie "user_info" should not be set

  Scenario: Signing out does not end the session at the provider
    Given I sign in as a super administrator
    When I navigate to "/auth/logout?redirect=/auth/login"
    Then the cookie "access_token" should be set
