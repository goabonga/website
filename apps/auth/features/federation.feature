Feature: Identity provider federation
    As an organisation administrator
    I want my members to sign in with my corporate identity provider
    So that they do not need a separate password for the service

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And identity provider secrets are encrypted with a fresh key
        And the test client talks plain HTTP
        And the platform tenant "platform" exists
        And the tenant "acme" exists
        And the tenant "acme" has its default roles
        And the tenant "acme" has an OpenID Connect provider "Acme SSO"
        And the visitor browses the tenant "acme" at "acme.auth.example.test"

    Scenario: The sign-in options of a tenant are listed
        When I send a GET request to "/federation/providers?tenant_slug=acme"
        Then the response status is 200
        And the response JSON field "tenant_slug" is "acme"
        And the providers include "Acme SSO" with the button text "Continue with Acme SSO"

    Scenario: The visitor is sent to the identity provider with PKCE
        When the visitor starts the sign-in with "Acme SSO" and returns to "/portal"
        Then the visitor is redirected to the identity provider authorization endpoint
        And the authorization request carries the client id, the callback URL, a state, a nonce and an S256 code challenge

    Scenario: A first sign-in provisions the user and opens a session
        Given the visitor started the sign-in with "Acme SSO" and returns to "/portal"
        When the identity provider sends the visitor back with the code "abc" for "bob@example.com"
        Then the visitor is redirected to "/portal?state=" followed by the original state
        And the response sets an HttpOnly session cookie named "session_acme"
        And the user "bob@example.com" exists with a verified address
        And the user "bob@example.com" is a member of the tenant "acme"
        And the identity provider received the code "abc", the client secret and the PKCE verifier

    Scenario: A returning user is recognised
        Given the visitor signed in with "Acme SSO" as "bob@example.com"
        When the visitor signs in again with "Acme SSO" as "bob@example.com"
        Then there is exactly 1 user with the address "bob@example.com"
        And the user has 1 federated identity

    Scenario: A matching local account is linked
        Given a verified user "bob@example.com" with the password "Sup3r!secret"
        When the visitor signs in with "Acme SSO" as "bob@example.com"
        Then there is exactly 1 user with the address "bob@example.com"
        And the user has 1 federated identity

    Scenario: Providers can refuse to create accounts
        Given the provider "Acme SSO" does not provision accounts
        When the visitor signs in with "Acme SSO" as "carol@example.com"
        Then the visitor is redirected to a path starting with "/auth/login?error=federation_failed"
        And there is no user with the address "carol@example.com"

    Scenario: An error reported by the identity provider is shown on the login page
        When the identity provider reports the error "access_denied"
        Then the visitor is redirected to a path starting with "/auth/login?error=federation_failed"

    Scenario Outline: Broken callbacks are refused
        When the visitor opens the callback "<query>"
        Then the response status is <status>

        Examples:
            | query                  | status |
            | code=abc               | 400    |
            | code=abc&state=garbage | 400    |

    Scenario: Unknown or inactive providers cannot be used
        When the visitor starts the sign-in with the unknown provider "00000000-0000-0000-0000-000000000000"
        Then the response status is 404
        Given the provider "Acme SSO" is switched off
        When the visitor starts the sign-in with "Acme SSO" and returns to "/portal"
        Then the response status is 400
