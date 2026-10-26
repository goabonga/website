Feature: OAuth2 client credentials for downstream calls
  As the webhooks gateway
  I want to authenticate against internal services with an OAuth2 token
  So that they can enforce scope-based access control on their webhook endpoints

  Scenario: Static token is used when OAuth2 is not configured
    Given OAuth2 client credentials are not configured
    When the gateway builds the authorization header with static token "legacy-token"
    Then the authorization header should be "Bearer legacy-token"

  Scenario: No header is built without any credentials
    Given OAuth2 client credentials are not configured
    When the gateway builds the authorization header without static token
    Then there should be no authorization header

  Scenario: Access token is acquired from the token endpoint
    Given OAuth2 client credentials are configured
    And the token endpoint issues the access token "oauth-access-token"
    When the gateway builds the authorization header with static token "legacy-token"
    Then the authorization header should be "Bearer oauth-access-token"
    And the token endpoint should have been called once

  Scenario: Access token is cached between calls
    Given OAuth2 client credentials are configured
    And the token endpoint issues the access token "oauth-access-token"
    When the gateway builds the authorization header twice
    Then the token endpoint should have been called once

  Scenario: Static token is the fallback when the token endpoint fails
    Given OAuth2 client credentials are configured
    And the token endpoint answers with status 500
    When the gateway builds the authorization header with static token "legacy-token"
    Then the authorization header should be "Bearer legacy-token"
