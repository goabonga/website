Feature: OAuth2 bearer authentication
  As the operator of the statistics API
  I want protected routes to require a valid bearer token with the right scopes
  So that only authorised clients can read or change analytics data

  Background:
    Given a protected application with the routes "/read" and "/write"

  Scenario: A request without token is rejected
    When I request the protected route "/read" without a token
    Then the response status code should be 401
    And the response should contain "Missing authorization token"

  Scenario: An invalid token is rejected
    When I request the protected route "/read" with the token "garbage"
    Then the response status code should be 401
    And the response should contain "Invalid token"

  Scenario: A revoked token is rejected
    When I request the protected route "/read" with the token "revoked"
    Then the response status code should be 401
    And the response should contain "Token has been revoked"

  Scenario: A token with the required scope is accepted
    Given the token "reader" grants the scopes "analytics:read"
    When I request the protected route "/read" with the token "reader"
    Then the response status code should be 200
    And the response JSON key "scopes" should equal "['analytics:read']"

  Scenario: A token without the required scope is forbidden
    Given the token "reader" grants the scopes "analytics:read"
    When I request the protected route "/write" with the token "reader"
    Then the response status code should be 403
    And the response should contain "Insufficient scopes"
    And the response header "WWW-Authenticate" should contain "insufficient_scope"

  Scenario: A resource wildcard grants every scope of the resource
    Given the token "admin" grants the scopes "analytics:*"
    When I request the protected route "/write" with the token "admin"
    Then the response status code should be 200

  Scenario: The global wildcard grants every scope
    Given the token "root" grants the scopes "*"
    When I request the protected route "/write" with the token "root"
    Then the response status code should be 200

  Scenario: A machine token is recognised
    Given the token "robot" is issued to the client "analytics-cron" with the scopes "analytics:read"
    When I request the protected route "/read" with the token "robot"
    Then the response status code should be 200
    And the response JSON key "machine" should equal "True"

  Scenario: The current user is built from the token claims
    Given the token "alice" belongs to the user "alice@example.com" with the scopes "openid"
    When I request the protected route "/me" with the token "alice"
    Then the response status code should be 200
    And the response JSON key "email" should equal "alice@example.com"

  Scenario: Scopes can be checked with token exchange
    Given token exchange is configured and grants "analytics:read"
    When I request the protected route "/read" with the token "anything"
    Then the response status code should be 200

  Scenario: Token exchange refuses missing scopes
    Given token exchange is configured and answers "insufficient_scope"
    When I request the protected route "/write" with the token "anything"
    Then the response status code should be 403

  Scenario: Token exchange refuses expired tokens
    Given token exchange is configured and answers "invalid_grant"
    When I request the protected route "/read" with the token "anything"
    Then the response status code should be 401

  Scenario: Protected routes answer 503 when no issuer is configured
    Given no OAuth2 issuer is configured
    When I request the protected route "/read" with the token "reader"
    Then the response status code should be 503
