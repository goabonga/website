Feature: Device authorization and pushed authorization requests
    As the developer of an input-constrained device or of a security-sensitive web client
    I want the device flow and pushed authorization requests
    So that a TV can sign in through a phone and a backend can keep its authorization parameters private

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And a signing key store protected by a fresh encryption key
        And the operator generated and activated a signing key
        And the issuer is configured as "https://auth.example.com"
        And the test client talks plain HTTP
        And the platform tenant "platform" exists
        And a verified user "alice@example.com" with the password "Sup3r!secret"
        And a public client "tv" for the device flow with the scopes "openid profile"
        And a confidential client "backend" with the scopes "openid profile email" that skips consent

    Scenario: A device obtains tokens once the user approves it on another screen
        Given the device polling interval is 0 seconds
        When the device requests a device code for the scopes "openid"
        Then the response status is 200
        And the device authorization contains a device code, a user code and a verification URI
        When the device polls the token endpoint
        Then the response status is 400
        And the token error is "authorization_pending"
        When I sign in through the API as "alice@example.com" with the password "Sup3r!secret"
        And the user opens the verification page for the user code
        Then the response status is 200
        When the user submits the user code
        Then the response status is 200
        When the user approves the device
        Then the response status is 200
        When the device polls the token endpoint
        Then the response status is 200
        And the token response contains an access token
        When the device polls the token endpoint
        Then the response status is 400
        And the token error is "invalid_grant"

    Scenario: A denied device never receives tokens
        Given the device polling interval is 0 seconds
        And the device requested a device code for the scopes "openid"
        And I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        When the user denies the device
        And the device polls the token endpoint
        Then the response status is 400
        And the token error is "access_denied"

    Scenario: Polling faster than the interval is told to slow down
        Given the device requested a device code for the scopes "openid"
        And the device polled a moment ago
        When the device polls the token endpoint
        Then the response status is 400
        And the token error is "slow_down"

    Scenario: An expired device code is refused
        Given the device polling interval is 0 seconds
        And the device requested a device code for the scopes "openid"
        And the device code expired
        When the device polls the token endpoint
        Then the response status is 400
        And the token error is "expired_token"

    Scenario: The verification page requires a signed-in user
        Given the device requested a device code for the scopes "openid"
        When the user opens the verification page for the user code
        Then the browser is redirected to a path starting with "/auth/login"

    Scenario: A wrong user code is rejected
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        When the user submits the user code "ZZZZ-9999"
        Then the response status is 200
        And the response body contains "Invalid"

    Scenario: A client that is not allowed the device grant cannot start the flow
        When the confidential client "backend" requests a device code
        Then the response status is 400
        And the token error is "unauthorized_client"

    Scenario: A pushed authorization request is exchanged for a single-use reference
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        When the client "backend" pushes an authorization request for the scopes "openid email"
        Then the response status is 200
        And the response JSON field "expires_in" is "60"
        And the response carries a request URI
        When the browser follows the request URI
        Then the browser is redirected to the client with a code and the state "xyz"
        When the browser follows the request URI
        Then the response status is 400
        And the response is an HTML error page

    Scenario: Pushing a request requires client authentication
        When the client "backend" pushes an authorization request with the wrong secret
        Then the response status is 401

    Scenario: A pushed request is validated like a direct one
        When the client "backend" pushes an authorization request for the scopes "admin"
        Then the response status is 400
        And the token error is "invalid_scope"
