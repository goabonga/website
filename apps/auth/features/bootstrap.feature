Feature: Platform bootstrap
    As an operator
    I want the platform tenant, the Swagger UI client and the built-in roles created from my settings
    So that a fresh database is usable after the migrations, with no deployment value in the code

    Background:
        Given an empty user database

    Scenario: A fresh database receives the built-in scopes and roles
        When I run "auth bootstrap"
        Then the command exits with 0
        And the command prints "created role super_admin with 1 scope(s)"
        And the scope "users:read" exists in the category "admin" with the description "View user information (list, details)"
        And the scope "org:write" exists in the category "admin" with the description "Create and update organisations, their members and identity providers"
        And the role "super_admin" holds the scopes "*"
        And the role "operator" holds the scopes "clients:read, sessions:read, sessions:revoke, users:read"

    Scenario: The platform tenant is created from the settings
        Given the setting "platform_tenant_slug" is "main-site"
        And the setting "platform_tenant_display_name" is "Main Site"
        And the platform tenant branding is {"primary_color": "#112233"}
        When I run "auth bootstrap"
        Then the command exits with 0
        And the command prints "created platform tenant main-site"
        And the platform tenant is "main-site" named "Main Site", open to all users and active
        And the platform tenant has the roles "owner, admin, member"
        And the platform tenant has the primary colour "#112233"

    Scenario: The identifier of the platform tenant can be chosen
        Given the setting "platform_tenant_id" is "6f1e0c2a-4a53-4a52-9d0f-0a7d3c6b9e11"
        When I run "auth bootstrap"
        Then the platform tenant has the identifier "6f1e0c2a-4a53-4a52-9d0f-0a7d3c6b9e11"

    Scenario: Running it again changes nothing
        Given the bootstrap was run
        When I run "auth bootstrap --json"
        Then the command exits with 0
        And the JSON report says nothing changed
        And there is exactly 1 platform tenant

    Scenario: A dry run reports the changes and applies none
        When I run "auth bootstrap --dry-run"
        Then the command exits with 0
        And the command prints "would create platform tenant platform"
        And there is no platform tenant
        And no scope "users:read" exists

    Scenario: An existing platform tenant is adopted and not renamed
        Given the platform tenant "legacy" exists
        And the setting "platform_tenant_slug" is "main-site"
        When I run "auth bootstrap"
        Then the command exits with 0
        And the command prints "skipped platform tenant slug"
        And there is exactly 1 platform tenant
        And the platform tenant is "legacy" named "Legacy"

    Scenario: A slug used by another tenant is refused
        Given the tenant "main-site" exists
        And the setting "platform_tenant_slug" is "main-site"
        When I run "auth bootstrap"
        Then the command exits with 2
        And the command reports the error "not the platform tenant"
        And there is no platform tenant

    Scenario: Invalid settings are refused before the database is touched
        Given the setting "platform_tenant_slug" is "Not A Slug"
        When I run "auth bootstrap"
        Then the command exits with 2
        And the command reports the error "not a valid slug"
        And no scope "users:read" exists

    Scenario: Existing users are registered on the platform tenant and made members
        Given the bootstrap was run
        And a verified user "alice@example.com" with the password "Sup3r!secret"
        And a verified user "bob@example.com" with the password "Sup3r!secret" registered on the platform tenant
        When I run "auth bootstrap"
        Then the command exits with 0
        And the command prints "updated 1 user(s) registered on the platform tenant"
        And the command prints "updated 2 user(s) made member of the platform tenant"
        And "alice@example.com" is registered on the platform tenant and is a "member" of it
        And "bob@example.com" is registered on the platform tenant and is a "member" of it
        When I run "auth bootstrap --json"
        Then the JSON report says nothing changed

    Scenario: The Swagger UI client is created from the settings
        Given the setting "swagger_client_id" is "docs-client"
        And the setting "swagger_scopes" is "openid profile email *"
        And the setting "swagger_redirect_uris" is ["https://auth.example.test/docs/oauth2-redirect"]
        When I run "auth bootstrap"
        Then the command prints "created client docs-client"
        And the client "docs-client" is a public client that requires PKCE and no consent
        And the client "docs-client" is allowed the scopes "openid, profile, email, *"
        And the client "docs-client" is allowed the grant types "authorization_code"
        And the client "docs-client" redirects to "https://auth.example.test/docs/oauth2-redirect"

    Scenario: The Swagger UI client follows the settings when they change
        Given the bootstrap was run
        And the setting "swagger_scopes" is "openid"
        And the setting "swagger_redirect_uris" is ["https://other.example.test/cb"]
        When I run "auth bootstrap"
        Then the command prints "updated client swagger-ui (redirect URIs, scopes)"
        And the client "swagger-ui" is allowed the scopes "openid"
        And the client "swagger-ui" redirects to "https://other.example.test/cb"

    Scenario: The catalog of a deployment extends the built-in roles after the bootstrap
        Given the bootstrap was run
        And a catalog file:
            """
            {
              "scopes": [{"name": "notes:read"}],
              "roles": [{"name": "super_admin", "scopes": ["notes:read"]}]
            }
            """
        When I run "auth catalog sync" with the catalog file
        Then the role "super_admin" holds the scopes "*, notes:read"
