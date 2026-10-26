Feature: Authentication
  Protected endpoints validate the bearer token and the billing:* scopes.

  Background:
    Given a protected endpoint requiring scope "billing:platform:read"

  Scenario: A request without token is rejected
    When I call the protected endpoint without token
    Then the response status should be 401

  Scenario: An unknown token is rejected
    When I call the protected endpoint with token "unknown.bad.token"
    Then the response status should be 401

  Scenario: A token carrying the required scope is accepted
    Given a token "reader.jwt.token" with scopes "billing:platform:read"
    When I call the protected endpoint with token "reader.jwt.token"
    Then the response status should be 200
    And the response JSON "scopes" should be "['billing:platform:read']"

  Scenario: The billing wildcard scope grants every scope
    Given a token "admin.jwt.token" with scopes "billing:*"
    When I call the protected endpoint with token "admin.jwt.token"
    Then the response status should be 200

  Scenario: A token without the required scope is forbidden
    Given a token "writer.jwt.token" with scopes "billing:usage:write"
    When I call the protected endpoint with token "writer.jwt.token"
    Then the response status should be 403

  Scenario: An opaque token is validated by introspection
    Given a token "opaquetoken" with scopes "billing:platform:read"
    When I call the protected endpoint with token "opaquetoken"
    Then the response status should be 200
