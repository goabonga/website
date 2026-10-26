Feature: OAuth2 bearer authentication
  As an API client
  I want requests to be authenticated with a signed bearer token
  So that only users holding the right scopes can reach protected endpoints

  Background:
    Given an identity provider that signs tokens for the issuer "https://auth.example.test"
    And a protected endpoint requiring the scope "documents:read"

  Scenario: A request without a token is rejected
    When I call the protected endpoint without a token
    Then the response status code should be 401
    And the response field "detail" should be "Missing authentication"

  Scenario: A valid token carrying the required scope is accepted
    Given a signed token for user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "documents:read"
    When I call the protected endpoint with the token
    Then the response status code should be 200
    And the response field "user_id" should be "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

  Scenario: A token without the required scope is forbidden
    Given a signed token for user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "collections:read"
    When I call the protected endpoint with the token
    Then the response status code should be 403
    And the response field "detail" should be "Missing required scope: documents:read"

  Scenario: A wildcard scope grants every scope of its namespace
    Given a signed token for user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "documents:*"
    When I call the protected endpoint with the token
    Then the response status code should be 200

  Scenario: An expired token is rejected
    Given an expired token for user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "documents:read"
    When I call the protected endpoint with the token
    Then the response status code should be 401

  Scenario: A token signed by an unknown key is rejected
    Given a token signed by another key for user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "documents:read"
    When I call the protected endpoint with the token
    Then the response status code should be 401

  Scenario: The tenant header selects the tenant of the request
    Given a signed token for user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "documents:read"
    When I call the protected endpoint with the token and tenant "cccccccc-cccc-cccc-cccc-cccccccccccc"
    Then the response status code should be 200
    And the response field "tenant_id" should be "cccccccc-cccc-cccc-cccc-cccccccccccc"

  Scenario: A malformed tenant header is rejected
    Given a signed token for user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "documents:read"
    When I call the protected endpoint with the token and tenant "not-a-uuid"
    Then the response status code should be 400
