Feature: OAuth2 authentication
  Protected endpoints require a bearer token issued by the OAuth2 server and
  the scopes the endpoint asks for. The scenarios use a probe endpoint guarded
  by the scope dependency and a fake auth server, no network is involved.

  Background:
    Given a protected endpoint requiring the scope "custom-domain:read"

  Scenario: A request without a token is rejected
    Given I am not authenticated
    When I send a GET request to "/protected"
    Then the response status is 401

  Scenario: A token carrying the required scope is accepted
    Given I am authenticated as client "tenant-a" with scopes "custom-domain:read"
    When I send a GET request to "/protected"
    Then the response status is 200
    And the JSON field "client_id" equals "tenant-a"

  Scenario: A token without the required scope is rejected
    Given I am authenticated as client "tenant-a" with scopes "custom-domain:lookup"
    When I send a GET request to "/protected"
    Then the response status is 403

  Scenario: A wildcard scope grants access
    Given I am authenticated as client "tenant-a" with scopes "custom-domain:*"
    When I send a GET request to "/protected"
    Then the response status is 200

  Scenario: A revoked token is rejected
    Given the auth server reports every token as revoked
    When I send a GET request to "/protected"
    Then the response status is 401
    And the JSON field "detail" equals "Token has been revoked"

  Scenario: A machine token is recognised by its client_id subject
    Given I am authenticated as machine client "billing-service" with scopes "custom-domain:read"
    When I send a GET request to "/protected"
    Then the response status is 200
    And the JSON field "is_machine_client" is true
