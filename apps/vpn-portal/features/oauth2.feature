Feature: OAuth2 token validation and scope checks
  As the portal
  I want to validate bearer tokens and the scopes they carry
  So that only authorized users reach protected routes

  Background:
    Given a protected application with a route requiring the "vpn:connect" scope
    And OAuth2 is configured

  Scenario: Request without a token
    When I send a GET request to "/protected"
    Then the response status code should be 401

  Scenario: JWT carrying the required scope
    Given I present a JWT granting "vpn:connect openid"
    When I send a GET request to "/protected"
    Then the response status code should be 200
    And the response should contain "scopes" with value "['vpn:connect', 'openid']"

  Scenario: JWT missing the required scope
    Given I present a JWT granting "openid profile"
    When I send a GET request to "/protected"
    Then the response status code should be 403

  Scenario: Wildcard scope covers the required scope
    Given I present a JWT granting "vpn:*"
    When I send a GET request to "/protected"
    Then the response status code should be 200

  Scenario: Revoked token
    Given I present a revoked JWT
    When I send a GET request to "/protected"
    Then the response status code should be 401
    And the response should contain "detail" with value "Token has been revoked"

  Scenario: Invalid token signature
    Given I present a JWT with an invalid signature
    When I send a GET request to "/protected"
    Then the response status code should be 401
    And the response should contain "detail" with value "Invalid token"

  Scenario: Opaque personal access token
    Given I present an opaque token granting "vpn:connect"
    When I send a GET request to "/protected"
    Then the response status code should be 200

  Scenario: Token exchange grants the scope
    Given token exchange is configured and grants "vpn:connect"
    And I present a JWT granting "openid"
    When I send a GET request to "/protected"
    Then the response status code should be 200
    And the response should contain "scopes" with value "['vpn:connect']"

  Scenario: Token exchange refuses the scope
    Given token exchange is configured and refuses the scope
    And I present a JWT granting "openid"
    When I send a GET request to "/protected"
    Then the response status code should be 403

  Scenario: OAuth2 is not configured
    Given OAuth2 is not configured
    And I present a JWT granting "vpn:connect"
    When I send a GET request to "/protected"
    Then the response status code should be 503

  Scenario: Machine client token
    Given a client_credentials claim set for client "openvpn-server" with scope "vpn:server"
    When the user is built from the claims
    Then the user should be a machine client
    And the user should have the scope "vpn:server"

  Scenario: User token
    Given a user claim set with a UUID subject and scope "vpn:connect"
    When the user is built from the claims
    Then the user should not be a machine client
    And the user should have the scope "vpn:connect"
