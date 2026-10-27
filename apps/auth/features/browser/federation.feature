@browser
Feature: Identity provider federation in a browser
    As a member of an organisation
    I want to sign in with the identity provider of my organisation
    So that I do not need a separate password for the service

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And identity provider secrets are encrypted with a fresh key
        And the application is served at its public address
        And the platform tenant "platform" exists
        And the tenant "acme" exists
        And the tenant "acme" has its default roles
        And an external identity provider with the user "bob@example.com" and the password "idp-secret-1"
        And the tenant "acme" trusts the external identity provider as "Acme SSO"
        And the tenants of the application are served by path

    Scenario: A first sign-in at the identity provider provisions the user and opens a session
        When the visitor starts the sign-in with "Acme SSO" for the tenant "acme" returning to "/auth/mfa/status"
        Then the browser is at the identity provider
        And the page title should contain "Sign in"
        When the visitor signs in at the identity provider
        Then the URL should contain "/auth/mfa/status?state=orig-state"
        And I should see "totp_enabled"
        And the session cookie of the browser is HttpOnly, Secure and SameSite Lax
        And the user "bob@example.com" exists with a verified address
        And the user "bob@example.com" is a member of the tenant "acme"
        And the session cookie of the browser belongs to "bob@example.com"
        And the identity provider received the code, the client secret and a PKCE verifier

    Scenario: A returning user is recognised and a wrong password stays at the provider
        Given the visitor started the sign-in with "Acme SSO" for the tenant "acme" returning to "/auth/mfa/status"
        And the visitor signs in at the identity provider
        And the identity provider forgot its sessions
        When the visitor starts the sign-in with "Acme SSO" for the tenant "acme" returning to "/auth/mfa/status"
        And the visitor signs in at the identity provider with the password "wrong"
        Then I should see "Invalid email or password."
        And the browser is at the identity provider
        When the visitor signs in at the identity provider
        Then the URL should contain "/auth/mfa/status?state=orig-state"
        And there is exactly 1 user with the address "bob@example.com"
        And the user has 1 federated identity

    Scenario: A matching local account is linked to the identity
        Given a verified user "bob@example.com" with the password "Sup3r!secret"
        When the visitor starts the sign-in with "Acme SSO" for the tenant "acme" returning to "/auth/mfa/status"
        And the visitor signs in at the identity provider
        Then the URL should contain "/auth/mfa/status"
        And there is exactly 1 user with the address "bob@example.com"
        And the user has 1 federated identity

    Scenario: A provider that does not provision accounts leaves the visitor on the login page
        Given the provider "Acme SSO" does not provision accounts
        When the visitor starts the sign-in with "Acme SSO" for the tenant "acme" returning to "/auth/mfa/status"
        And the visitor signs in at the identity provider
        Then the URL should contain "/auth/login?error=federation_failed"
        And I should see "Sign-in with your identity provider failed"
        And there is no user with the address "bob@example.com"
        And the browser holds no session cookie

    Scenario: A provider that is switched off cannot be used
        Given the provider "Acme SSO" is switched off
        When the visitor starts the sign-in with "Acme SSO" for the tenant "acme" returning to "/auth/mfa/status"
        Then I should see "Identity provider is not active"
