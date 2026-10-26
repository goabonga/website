Feature: Token exchange for scope validation
  As the owner of the robot data
  I want the auth server to decide which scopes a token is granted
  So that scopes can be managed centrally

  Background:
    Given token exchange is configured with a confidential client

  Scenario: The auth server grants the required scope
    Given I am authenticated with scope "openid"
    And the auth server answers the token exchange with status 200
    When I request "GET /api/reports/quick"
    Then the response status code should be 200
    And the auth server should have been asked for the scope "reachy:reports:read"

  Scenario: The auth server refuses the scope
    Given I am authenticated with scope "reachy:reports:read"
    And the auth server answers the token exchange with the error "insufficient_scope"
    When I request "GET /api/reports/quick"
    Then the response status code should be 403

  Scenario: The auth server rejects the token
    Given I am authenticated with scope "reachy:reports:read"
    And the auth server answers the token exchange with the error "invalid_grant"
    When I request "GET /api/reports/quick"
    Then the response status code should be 401

  Scenario: The exchange result is cached
    Given I am authenticated with scope "openid"
    And the auth server answers the token exchange with status 200
    And a Redis cache is available for token exchange
    When I request "GET /api/reports/quick"
    And I request "GET /api/reports/quick"
    Then the response status code should be 200
    And the auth server should have received 1 exchange request

  Scenario: Opaque tokens skip the exchange
    Given the auth server answers the token exchange with status 200
    And I use an active opaque token with the scopes "reachy:reports:read"
    When I request "GET /api/reports/quick"
    Then the response status code should be 200
    And the auth server should have received 0 exchange request
