Feature: OIDC authentication
  API clients authenticate with a bearer token, either a signed JWT or an
  opaque personal access token, validated against the auth service.

  Scenario: A request without a token is rejected
    Given the auth service is configured
    When I request "/me"
    Then the response status is 401

  Scenario: The service reports when OAuth2 is not configured
    When I call "/me" using bearer token "a.b.c"
    Then the response status is 503

  Scenario: A valid JWT identifies the caller
    Given the auth service is configured
    And the auth service accepts token "aaa.bbb.ccc" for user "alice" with scopes "apt:read apt:write"
    And the profile of the token owner has email "alice@example.com"
    When I call "/me" using bearer token "aaa.bbb.ccc"
    Then the response status is 200
    And the JSON field "email" is "alice@example.com"
    And the JSON field "scopes" is "['apt:read', 'apt:write']"

  Scenario: A personal access token is validated by introspection
    Given the auth service is configured
    And the auth service accepts token "gab_pat_secret" for user "ci-bot" with scopes "apt:write"
    And the profile of the token owner has email "ci@example.com"
    When I call "/me" using bearer token "gab_pat_secret"
    Then the response status is 200
    And the JSON field "user_id" is "ci-bot"

  Scenario: A revoked token is refused
    Given the auth service is configured
    And the auth service has revoked token "aaa.bbb.ccc"
    When I call "/me" using bearer token "aaa.bbb.ccc"
    Then the response status is 401
    And the JSON field "detail" is "Token has been revoked"

  Scenario: An unknown token is refused
    Given the auth service is configured
    When I call "/me" using bearer token "zzz.yyy.xxx"
    Then the response status is 401
    And the JSON field "detail" is "Invalid token"
