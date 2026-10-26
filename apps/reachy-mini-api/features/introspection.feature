Feature: Token introspection
  As the owner of the robot data
  I want revoked tokens to be refused and opaque tokens to be accepted
  So that access can be withdrawn at the auth server

  Background:
    Given token introspection is configured

  Scenario: An active opaque token is accepted
    Given the introspection endpoint reports tokens as "active" with the scopes "reachy:reports:read"
    And I use the opaque token "ory_pat_good"
    When I request "GET /api/reports/quick"
    Then the response status code should be 200

  Scenario: An inactive opaque token is rejected
    Given the introspection endpoint reports tokens as "inactive" with the scopes "reachy:reports:read"
    And I use the opaque token "ory_pat_revoked"
    When I request "GET /api/reports/quick"
    Then the response status code should be 401
    And the response JSON field "detail" should be "Token has been revoked"

  Scenario: An opaque token without the scope is forbidden
    Given the introspection endpoint reports tokens as "active" with the scopes "openid"
    And I use the opaque token "ory_pat_other"
    When I request "GET /api/reports/quick"
    Then the response status code should be 403

  Scenario: A revoked JWT is rejected
    Given I am authenticated with scope "reachy:reports:read"
    And the introspection endpoint reports tokens as "inactive" with the scopes "reachy:reports:read"
    When I request "GET /api/reports/quick"
    Then the response status code should be 401
    And the response JSON field "detail" should be "Token has been revoked"

  Scenario: A JWT stays valid when the introspection endpoint is unreachable
    Given I am authenticated with scope "reachy:reports:read"
    And the introspection endpoint is unreachable
    When I request "GET /api/reports/quick"
    Then the response status code should be 200

  Scenario: The introspection result is cached
    Given I am authenticated with scope "reachy:reports:read"
    And the introspection endpoint reports tokens as "active" with the scopes "reachy:reports:read"
    And a Redis cache is available
    When I request "GET /api/reports/quick"
    And I request "GET /api/reports/quick"
    Then the response status code should be 200
    And the introspection endpoint should have been called 1 time
