Feature: OAuth2 token authentication
  As an API client
  I want my bearer token validated and its scopes enforced
  So that protected resources are only available to authorised callers

  Background:
    Given a protected API with the routes "/me" and "/admin"

  Scenario: Request without a token is rejected
    When I send a GET request to "/me"
    Then the response status code should be 401
    And the response JSON should contain "detail" with value "Missing authorization token"

  Scenario: OAuth2 not configured returns service unavailable
    Given OAuth2 is not configured
    When I request "/me" with the bearer token "aaa.bbb.ccc"
    Then the response status code should be 503

  Scenario: Valid JWT identifies the user
    Given the token "aaa.bbb.ccc" is valid with the claims:
      | claim | value                                |
      | sub   | 12345678-1234-5678-1234-567812345678 |
      | email | alice@example.com                    |
      | scope | openid profile                       |
    When I request "/me" with the bearer token "aaa.bbb.ccc"
    Then the response status code should be 200
    And the response JSON should contain "email" with value "alice@example.com"

  Scenario: Revoked token is rejected
    Given the token "aaa.bbb.ccc" has been revoked
    When I request "/me" with the bearer token "aaa.bbb.ccc"
    Then the response status code should be 401
    And the response JSON should contain "detail" with value "Token has been revoked"

  Scenario: Missing scope is forbidden
    Given the token "aaa.bbb.ccc" is valid with the claims:
      | claim | value                                |
      | sub   | 12345678-1234-5678-1234-567812345678 |
      | scope | openid profile                       |
    When I request "/admin" with the bearer token "aaa.bbb.ccc"
    Then the response status code should be 403

  Scenario: Wildcard scope grants access
    Given the token "aaa.bbb.ccc" is valid with the claims:
      | claim | value                                |
      | sub   | 12345678-1234-5678-1234-567812345678 |
      | scope | api:*                                |
    When I request "/admin" with the bearer token "aaa.bbb.ccc"
    Then the response status code should be 200
