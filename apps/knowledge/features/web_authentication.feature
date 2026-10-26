Feature: Web authentication and account pages
  As a visitor of the web application
  I want to sign up, sign in and manage my account
  So that I can use my workspace from a browser

  Background:
    Given the web authentication settings
    And an authentication service
    And the web database is in memory

  Scenario: The login page redirects to the authorization endpoint with PKCE
    When I open "/auth/login"
    Then the response status code should be 302
    And I should be redirected to the authorization endpoint of the issuer
    And the authorization request should use the S256 code challenge method
    And the browser should receive the cookies "oauth_state, oauth_code_verifier, oauth_redirect"

  Scenario: The login page reports a missing OAuth2 configuration
    Given OAuth2 is not configured
    When I open "/auth/login"
    Then the response status code should be 500
    And the page should say "Configuration Error"

  Scenario: The callback rejects a state that does not match
    When the identity provider redirects back with state "wrong" while the browser holds state "expected"
    Then the response status code should be 400

  Scenario: The first login creates a personal workspace and signs the user in
    Given the identity provider issues tokens for user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" named "Alice"
    When the identity provider redirects back with a valid code
    Then the response status code should be 302
    And I should be redirected to "/dashboard"
    And the browser should receive the cookies "access_token, refresh_token, active_tenant_id, user_info"
    And a free workspace "Alice's Workspace" should have been created for the user

  Scenario: Logging out clears the session cookies
    When I open "/auth/logout"
    Then the response status code should be 302
    And I should be redirected to "/"
    And the browser should be told to delete the cookies "access_token, refresh_token, active_tenant_id"

  Scenario: The signup form is displayed
    When I open "/auth/signup"
    Then the response status code should be 200
    And the page should say "Create"

  Scenario: Signup requires matching passwords
    When I sign up as "alice@example.test" with password "secret-1" and confirmation "secret-2"
    Then the response status code should be 400
    And the page should say "Passwords do not match"

  Scenario: A successful signup leads to email verification
    When I sign up as "alice@example.test" with password "secret-1" and confirmation "secret-1"
    Then the response status code should be 303
    And I should be redirected to a URL starting with "/auth/verify?email=alice%40example.test"
    And the authentication service should have registered "alice@example.test"

  Scenario: Signing up with an existing email leads to signin
    Given the email "alice@example.test" is already registered
    When I sign up as "alice@example.test" with password "secret-1" and confirmation "secret-1"
    Then the response status code should be 303
    And I should be redirected to a URL starting with "/auth/signin?email=alice%40example.test"

  Scenario: Email verification accepts the right code
    When I verify "alice@example.test" with the code "123456"
    Then the response status code should be 303
    And I should be redirected to a URL starting with "/auth/signin?verified=1"

  Scenario: Email verification rejects a wrong code
    Given the verification code is wrong
    When I verify "alice@example.test" with the code "000000"
    Then the response status code should be 400
    And the page should say "Invalid verification code"

  Scenario: Signin with wrong credentials shows an error
    Given the credentials are wrong
    When I sign in as "alice@example.test" with password "bad"
    Then the response status code should be 400
    And the page should say "Invalid email or password"

  Scenario: Signin without a workspace asks the user to create one
    Given the identity provider issues tokens for user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" named "Alice"
    When I sign in as "alice@example.test" with password "secret-1"
    Then the response status code should be 302
    And I should be redirected to "/auth/create-workspace"
    And the browser should receive the cookies "access_token, user_info"

  Scenario: Signin after signup creates the chosen workspace
    Given the identity provider issues tokens for user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" named "Alice"
    When I sign in as "alice@example.test" using password "secret-1" to create the workspace "Team Space"
    Then the response status code should be 302
    And I should be redirected to "/dashboard"
    And a free workspace "Team Space" should have been created for the user
    And the browser should receive the cookies "access_token, active_tenant_id"

  Scenario: Signin asks for a second factor when the account requires one
    Given the account requires a second factor
    When I sign in as "alice@example.test" with password "secret-1"
    Then the response status code should be 400
    And the page should say "Enter your authenticator or backup code"
    And the browser should receive the cookies "knowledge_mfa_signin_challenge"

  Scenario: Forgotten passwords never reveal whether the account exists
    Given no account exists for "ghost@example.test"
    When I ask for a password reset for "ghost@example.test"
    Then the response status code should be 200
    And the page should say "If an account exists with this email"

  Scenario: Resetting a password needs a token
    When I open "/auth/reset-password"
    Then the response status code should be 400
    And the page should say "Invalid or missing reset token"

  Scenario: A password reset leads back to signin
    When I reset the password with the token "abc" and the new password "n3w-secret"
    Then the response status code should be 303
    And I should be redirected to "/auth/signin?reset=1"

  Scenario: Account pages require a signed-in user
    When I open "/auth/account"
    Then the response status code should be 302
    And I should be redirected to a URL starting with "/auth/login"

  Scenario: A signed-in user sees their profile
    Given I am signed in as "Alice" with the nickname "ally"
    When I open "/auth/account"
    Then the response status code should be 200
    And the page should say "ally"

  Scenario: A signed-in user updates their profile
    Given I am signed in as "Alice" with the nickname "ally"
    When I update my profile nickname to "alice2"
    Then the response status code should be 303
    And I should be redirected to a URL starting with "/auth/account?success="
    And the authentication service should have updated the nickname to "alice2"
