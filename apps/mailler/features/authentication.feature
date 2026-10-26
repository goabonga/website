Feature: OAuth2 authentication
  Protected routes require a bearer token carrying the right mailler scopes.
  Scopes ending with a wildcard grant every scope of their namespace.

  Scenario: A request without a token is rejected
    Given I am not authenticated
    When I send a GET to "/__probe/read"
    Then the response status should be 401

  Scenario: A token holding the required scope is accepted
    Given I am authenticated with scopes "mailler:read"
    When I send a GET to "/__probe/read"
    Then the response status should be 200
    And the response JSON should contain "user_id"

  Scenario: A token without the required scope is forbidden
    Given I am authenticated with scopes "mailler:read"
    When I send a GET to "/__probe/send"
    Then the response status should be 403

  Scenario: The wildcard scope grants every mailler scope
    Given I am authenticated
    When I send a GET to "/__probe/send"
    Then the response status should be 200

  Scenario: A wildcard of another namespace grants nothing
    Given I am authenticated with scopes "other:*"
    When I send a GET to "/__probe/read"
    Then the response status should be 403

  Scenario: A revoked token is rejected
    Given I am authenticated with a revoked token
    When I send a GET to "/__probe/read"
    Then the response status should be 401

  Scenario: An unknown token is rejected
    Given I am authenticated with an unknown token
    When I send a GET to "/__probe/read"
    Then the response status should be 401

  Scenario: An opaque personal access token is validated by introspection
    Given I am authenticated with an opaque token
    When I send a GET to "/__probe/read"
    Then the response status should be 200

  Scenario: Authentication is unavailable when the OAuth2 provider is not configured
    Given I am authenticated
    And the OAuth2 provider is not configured
    When I send a GET to "/__probe/read"
    Then the response status should be 503

  Scenario: The health check stays public
    Given I am not authenticated
    When I send a GET to "/health"
    Then the response status should be 200

  Scenario: The caller is identified by the client the token was issued to
    Given I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/__probe/client"
    Then the response status should be 200
    And the response JSON "client_id" should be "app-one"
    And the response JSON "is_admin" should be false

  Scenario: The authorized party identifies the client when no client id is carried
    Given I am authenticated with only the authorized party "app-two" and scopes "mailler:read"
    When I send a GET to "/__probe/client"
    Then the response status should be 200
    And the response JSON "client_id" should be "app-two"

  Scenario: A token without client identity is refused
    Given I am authenticated without client identity with scopes "mailler:read"
    When I send a GET to "/__probe/client"
    Then the response status should be 403

  Scenario: The administration scope crosses the client boundary
    Given I am authenticated as client "ops" with scopes "mailler:read mailler:admin"
    When I send a GET to "/__probe/client"
    Then the response status should be 200
    And the response JSON "is_admin" should be true

  Scenario: The wildcard scope also grants administration
    Given I am authenticated
    When I send a GET to "/__probe/client"
    Then the response JSON "is_admin" should be true

  Scenario: An administrator does not need a client identity
    Given I am authenticated without client identity with scopes "mailler:read mailler:admin"
    When I send a GET to "/__probe/client"
    Then the response status should be 200
