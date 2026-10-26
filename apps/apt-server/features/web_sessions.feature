Feature: Web login sessions
  Browser users sign in with the OAuth2 Authorization Code flow and PKCE. A
  signed session cookie then identifies them on pages and APIs.

  Background:
    Given the repository serves components "main,private" of which "main" is public
    And the identity provider is configured with web client "web-client"

  @database
  Scenario: Login redirects to the identity provider
    When I start the web login
    Then the response status is 307
    And the response redirects to the authorization endpoint with a PKCE challenge
    And the OAuth state cookie is set

  @database
  Scenario: Completing the login creates a session
    Given the identity provider knows user "u-1" with email "alice@example.com"
    When I start the web login
    And I return from the identity provider with a valid code
    Then the response status is 302
    And the response redirects to "/"
    And a session cookie is set for "alice@example.com"

  @database
  Scenario: A callback with a forged state is refused
    When I start the web login
    And I return from the identity provider with a forged state
    Then the response status is 400

  @database
  Scenario: A callback without the state cookie is refused
    When I return from the identity provider without the state cookie
    Then the response status is 400

  @database
  Scenario: A failed code exchange is reported as a bad gateway
    Given the identity provider rejects the authorization code
    When I start the web login
    And I return from the identity provider with a valid code
    Then the response status is 502

  @database
  Scenario: The session cookie opens private components
    Given the auth service accepts the session token "web-token" for user "u-1"
    And I have a session for "alice@example.com" with token "web-token"
    When I request "/dists/stable/private/binary-amd64/Packages" with my session
    Then the response status is 200

  @database
  Scenario: Without a session private components stay closed
    When I request "/dists/stable/private/binary-amd64/Packages"
    Then the response status is 401

  @database
  Scenario: Logging out clears the session cookie
    When I log out
    Then the response status is 302
    And the session cookie is cleared
