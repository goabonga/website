Feature: OAuth2 and OpenID Connect authorization server
    As the developer of a client application
    I want to delegate authentication to the service with standard OAuth2 and OpenID Connect flows
    So that my application never handles passwords and can verify tokens independently

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And a signing key store protected by a fresh encryption key
        And the operator generated and activated a signing key
        And the issuer is configured as "https://auth.example.com"
        And the test client talks plain HTTP
        And the platform tenant "platform" exists
        And a verified user "alice@example.com" with the password "Sup3r!secret"
        And a confidential client "demo" with the scopes "openid profile email introspect" that skips consent

    Scenario: The authorization code flow with PKCE issues verifiable tokens
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        When the client asks for an authorization code with the scopes "openid profile email"
        Then the browser is redirected to the client with a code and the state "xyz"
        When the client exchanges the code with its credentials
        Then the response status is 200
        And the response JSON field "token_type" is "Bearer"
        And the token response contains an access token, a refresh token and an ID token
        And the access token is signed by a key published at the JWKS endpoint
        And the access token has the issuer "https://auth.example.com" and the scope "openid profile email"
        And the ID token carries the nonce "n-0S6"

    Scenario: The userinfo endpoint returns the claims allowed by the scopes
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        And the client obtained tokens for the scopes "openid email"
        When the client requests the userinfo with the access token
        Then the response status is 200
        And the response JSON field "email" is "alice@example.com"
        And the userinfo has no name claim

    Scenario: A code cannot be exchanged twice
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        And the client asks for an authorization code with the scopes "openid"
        And the client exchanges the code with its credentials
        When the client exchanges the same code again
        Then the response status is 400
        And the token error is "invalid_grant"

    Scenario: The PKCE verifier must match the challenge
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        And the client asks for an authorization code with the scopes "openid"
        When the client exchanges the code with a wrong verifier
        Then the response status is 400
        And the token error is "invalid_grant"

    Scenario: Unauthenticated users are sent to the login page
        When the client asks for an authorization code with the scopes "openid"
        Then the browser is redirected to a path starting with "/auth/login?next="

    Scenario: PKCE is mandatory for the client
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        When the client asks for an authorization code without a code challenge
        Then the browser is redirected to the client with the error "invalid_request"

    Scenario: Scopes outside the client allowance are refused
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        When the client asks for an authorization code with the scopes "admin"
        Then the browser is redirected to the client with the error "invalid_scope"

    Scenario: A group scope declared in the settings covers the scopes of its resources in a token exchange
        Given the scope group "suite:*" covers the resources "notes, tasks"
        Then a client allowed the scopes "openid suite:*" may be granted "notes:read"
        And a client allowed the scopes "openid suite:*" may be granted "tasks:write"
        And a client allowed the scopes "openid suite:*" may not be granted "billing:read"

    Scenario Outline: Authorization requests with an untrusted client or redirect URI show an error page
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        When the client asks for an authorization code with the client id "<client>" and the redirect URI "<redirect>"
        Then the response status is 400
        And the response is an HTML error page

        Examples:
            | client  | redirect                         |
            | unknown | https://app.example.com/callback |
            | demo    | https://evil.example.com/steal   |

    Scenario: A consent screen is shown to clients that require it
        Given a public client "spa" with the scopes "openid" that requires consent
        And I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        When the client "spa" asks for an authorization code with the scopes "openid"
        Then the response status is 200
        And the response body contains "spa"
        When the user approves the consent
        Then the browser is redirected to the client with a code and the state "xyz"
        When the client "spa" asks for an authorization code with the scopes "openid"
        And the user denies the consent
        Then the browser is redirected to the client with the error "access_denied"

    Scenario: The client credentials grant issues a machine token
        When the client requests a token with the client credentials grant for the scope "introspect"
        Then the response status is 200
        And the response JSON field "scope" is "introspect"
        And the token response has no refresh token

    Scenario Outline: Client authentication is enforced
        When the client requests a token with the client credentials grant using the secret "<secret>"
        Then the response status is <status>

        Examples:
            | secret | status |
            | wrong  | 401    |
            | -      | 401    |

    Scenario: A grant type the client was not given is refused
        When the client requests a token with the password grant
        Then the response status is 400
        And the token error is "unauthorized_client"

    Scenario: Refresh tokens are rotated and can be revoked
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        And the client obtained tokens for the scopes "openid"
        When the client refreshes the tokens
        Then the response status is 200
        And the response contains a new refresh token
        When the client refreshes the tokens with the previous refresh token
        Then the response status is 400
        When the client revokes the current refresh token
        Then the response status is 200
        When the client refreshes the tokens
        Then the response status is 400

    Scenario: Token introspection reports the state of a token
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        And the client obtained tokens for the scopes "openid email"
        When the client introspects the access token
        Then the response status is 200
        And the introspection says the token is active for "openid email"
        When the client revokes the access token
        And the client introspects the access token
        Then the introspection says the token is not active

    Scenario: Browser applications may call the token endpoint from registered origins only
        When a browser at "https://app.example.com" sends a preflight request to "/oauth2/token"
        Then the response allows the origin "https://app.example.com"
        When a browser at "https://evil.example.com" sends a preflight request to "/oauth2/token"
        Then the response does not allow any origin
