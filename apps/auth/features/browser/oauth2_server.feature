@browser
Feature: OAuth2 and OpenID Connect authorization in a browser
    As a user of a client application
    I want to sign in and to grant access on the pages of the authorization server
    So that the application receives an authorization code without ever seeing my password

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And a signing key store protected by a fresh encryption key
        And the operator generated and activated a signing key
        And the application is served at its public address
        And the platform tenant "platform" exists
        And a verified user "alice@example.com" with the password "Sup3r!secret"
        And a client application "demo" with the scopes "openid profile email introspect" that skips consent

    Scenario: A visitor signs in and is sent back to the client with an authorization code
        When the browser opens the authorization request of "demo" for the scopes "openid profile email"
        Then the URL should contain "/auth/login?next="
        And "Email" should be visible
        When I sign in as "alice@example.com" with the password "Sup3r!secret"
        Then the callback page of the client application received a code and the state sent
        When the client application redeems the code of the callback page
        Then the response status is 200
        And the token response contains an access token, a refresh token and an ID token
        And the access token is signed by a key published at the JWKS endpoint
        And the access token has the issuer of the application and the scope "openid profile email"
        And the ID token carries the nonce "n-0S6"

    Scenario: A user who is already signed in is not asked to sign in again
        Given a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        When the browser opens the authorization request of "demo" for the scopes "openid"
        Then the callback page of the client application received a code and the state sent

    Scenario: A client that requires consent shows the consent screen
        Given a client application "spa" with the scopes "openid email" that requires consent
        And a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        When the browser opens the authorization request of "spa" for the scopes "openid email"
        Then the page title should be "Authorize - spa"
        And I should see "Authorization Request"
        And I should see "Verify your identity"
        And I should see "Your email address"
        When I click "Allow"
        Then the callback page of the client application received a code and the state sent

    Scenario: Denying the consent sends an access_denied error to the client
        Given a client application "spa" with the scopes "openid" that requires consent
        And a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        When the browser opens the authorization request of "spa" for the scopes "openid"
        And I click "Deny"
        Then the callback page of the client application received the error "access_denied"

    Scenario: The code granted on the consent screen can be redeemed once
        Given a client application "spa" with the scopes "openid" that requires consent
        And a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        When the browser opens the authorization request of "spa" for the scopes "openid"
        And I click "Allow"
        Then the callback page of the client application received a code and the state sent
        When the client application redeems the code of the callback page
        Then the response status is 200
        When the client application redeems the same code again
        Then the token error is "invalid_grant"

    Scenario: A client asking for a scope outside its allowance gets an error redirect
        Given a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        When the browser opens the authorization request of "demo" for the scopes "admin"
        Then the callback page of the client application received the error "invalid_scope"

    Scenario: PKCE is mandatory
        Given a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        When the browser opens the authorization request of "demo" without a code challenge
        Then the callback page of the client application received the error "invalid_request"

    Scenario Outline: An untrusted client or redirect URI shows an error page and no redirect
        Given a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        And the browser records the pages it visits
        When the browser opens the authorization request with the client id "<client>" and the redirect URI "<redirect>"
        Then the browser stayed on the authorization server
        And the page title should contain "Error"

        Examples:
            | client  | redirect                         |
            | unknown | https://app.example.com/callback |
            | demo    | https://evil.example.com/steal   |

    Scenario: A browser application reads the keys and talks to the token endpoint from its registered origin
        Given a client application "spa" with the scopes "openid" that requires consent
        When the page of the client application "spa" calls "/.well-known/jwks.json" of the authorization server
        Then the browser let the page read the answer
        When the page of the client application "spa" calls "/.well-known/openid-configuration" of the authorization server
        Then the browser let the page read the answer
        When the page of the client application "spa" posts to the token endpoint for the client credentials
        Then the browser let the page read the answer

    Scenario: A page of an unregistered application is blocked by the browser
        Given a client application "spa" with the scopes "openid" that requires consent
        When a page of an unregistered application calls "/oauth2/token" of the authorization server
        Then the browser blocked the call to the authorization server
