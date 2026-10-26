Feature: JWT authentication with scope checks
  As the owner of the robot data
  I want every protected route to validate the bearer token and its scopes
  So that only authorized clients can read it

  Background:
    Given a protected route requiring the scope "resource:read"

  Scenario: A request without token is rejected
    When I send a GET request to "/protected"
    Then the response status code should be 401

  Scenario: A valid token carrying the scope is accepted
    Given a token issued by the primary issuer with the scopes "resource:read"
    When I send a GET request to "/protected" with that token
    Then the response status code should be 200

  Scenario: A valid token without the scope is forbidden
    Given a token issued by the primary issuer with the scopes "other:read"
    When I send a GET request to "/protected" with that token
    Then the response status code should be 403

  Scenario: A wildcard scope grants access
    Given a token issued by the primary issuer with the scopes "resource:*"
    When I send a GET request to "/protected" with that token
    Then the response status code should be 200

  Scenario: An expired token is rejected
    Given an expired token issued by the primary issuer with the scopes "resource:read"
    When I send a GET request to "/protected" with that token
    Then the response status code should be 401

  Scenario: A token from an unknown issuer is rejected
    Given a token issued by "https://evil.example.com" with the scopes "resource:read"
    When I send a GET request to "/protected" with that token
    Then the response status code should be 401

  Scenario: A token from a trusted additional issuer is accepted
    Given "https://partner.example.com" is a trusted issuer
    And a token issued by "https://partner.example.com" with the scopes "resource:read"
    When I send a GET request to "/protected" with that token
    Then the response status code should be 200
