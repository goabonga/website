Feature: OAuth2 authentication
  Routes are protected by bearer tokens issued by the authentication server.
  A dependency validates the token, checks the scopes of the route and
  exposes the authenticated user. The scenarios use a small application
  protected by the same dependency and an in-memory authentication server.

  Scenario: A request without a token is rejected
    Given a protected endpoint requiring the scope "team:platform:read"
    When I call the protected endpoint without a token
    Then the response status is 401
    And the response detail is "Missing authorization token"

  Scenario: A valid token with the required scope is accepted
    Given an authentication server that knows the user "6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11" with scopes "team:platform:read team:read"
    And a protected endpoint requiring the scope "team:platform:read"
    When I call the protected endpoint with the token "header.payload.signature"
    Then the response status is 200
    And the authenticated user id is "6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11"
    And the authenticated user is not a machine client

  Scenario: A token without the required scope is refused
    Given an authentication server that knows the user "6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11" with scopes "team:read"
    And a protected endpoint requiring the scope "team:platform:write"
    When I call the protected endpoint with the token "header.payload.signature"
    Then the response status is 403
    And the response detail is "Insufficient scopes. Missing: team:platform:write"

  Scenario: A wildcard scope grants every scope of its namespace
    Given an authentication server that knows the user "6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11" with scopes "team:*"
    And a protected endpoint requiring the scope "team:platform:write"
    When I call the protected endpoint with the token "header.payload.signature"
    Then the response status is 200

  Scenario: A wildcard scope does not grant another namespace
    Given an authentication server that knows the user "6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11" with scopes "team:*"
    And a protected endpoint requiring the scope "billing:read"
    When I call the protected endpoint with the token "header.payload.signature"
    Then the response status is 403

  Scenario: A machine client token is recognised
    Given an authentication server that knows the machine client "team-service" with scopes "team:write"
    And a protected endpoint requiring the scope "team:write"
    When I call the protected endpoint with the token "header.payload.signature"
    Then the response status is 200
    And the authenticated user id is "team-service"
    And the authenticated user is a machine client

  Scenario: A revoked token is refused
    Given an authentication server that revokes every token
    And a protected endpoint requiring the scope "team:read"
    When I call the protected endpoint with the token "header.payload.signature"
    Then the response status is 401
    And the response detail is "Token has been revoked"

  Scenario: A token rejected by the authentication server is refused
    Given an authentication server that rejects every token
    And a protected endpoint requiring the scope "team:read"
    When I call the protected endpoint with the token "header.payload.signature"
    Then the response status is 401
    And the response detail is "Invalid token"

  Scenario: An opaque token is validated by introspection only
    Given an authentication server that knows the user "6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11" with scopes "team:read"
    And a protected endpoint requiring the scope "team:read"
    When I call the protected endpoint with the token "opaque-personal-access-token"
    Then the response status is 200
    And the authentication server validated 1 opaque token

  Scenario: The service answers 503 when OAuth2 is not configured
    Given OAuth2 is not configured
    And a protected endpoint requiring the scope "team:read"
    When I call the protected endpoint with the token "header.payload.signature"
    Then the response status is 503

  Scenario: Token exchange refuses a token that lacks the scope
    Given an authentication server that knows the user "6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11" with scopes "team:read"
    And token exchange is enabled and denies the scope
    And a protected endpoint requiring the scope "team:platform:write"
    When I call the protected endpoint with the token "header.payload.signature"
    Then the response status is 403
    And the response detail is "Insufficient scopes. Required: team:platform:write"

  Scenario: Scopes can be listed in the token as a string or as a list
    When the user is built from the claims '{"sub": "u1", "scope": "a b"}'
    Then the user has the scopes "a, b"
    When the user is built from the claims '{"sub": "u1", "scp": ["c", "d"]}'
    Then the user has the scopes "c, d"
