@browser
Feature: Administration console in a browser
    As a platform administrator
    I want to operate users, scopes, roles, clients, organisations and signing keys from my browser
    So that nobody needs to call the API by hand

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And an encryption key is configured
        And the application is served at its public address
        And a verified user "root@example.com" with the password "Sup3r!secret"
        And a verified user "alice@example.com" with the password "Sup3r!secret"
        And "root@example.com" holds the administrator role
        And the browser records the dialogs of the page

    Scenario: Anonymous visitors are sent to the login page and come back after signing in
        When I navigate to "/admin/"
        Then the URL should contain "/auth/login"
        When I sign in as "root@example.com" with the password "Sup3r!secret"
        Then the URL should be "/admin/"
        And I should see "Dashboard"

    Scenario: A user without an administrator role is refused
        Given I navigate to "/auth/login?next=/admin/"
        When I sign in as "alice@example.com" with the password "Sup3r!secret"
        Then I should see "403"

    Scenario Outline: The sidebar opens every section of the console
        Given "root@example.com" signed in to the administration console
        When I open "<section>" from the sidebar
        Then the URL should contain "<path>"
        And I should see "<heading>"
        And the sidebar marks "<section>" as the current section
        And the browser should report no errors

        Examples:
            | section        | path                | heading                              |
            | JWKS Keys      | /admin/jwks         | JWKS Key Management                  |
            | Users          | /admin/users        | User Management                      |
            | OAuth2 Clients | /admin/clients      | OAuth2 Clients                       |
            | Sessions       | /admin/sessions     | Session Management                   |
            | Access Tokens  | /admin/pats         | Personal Access Token Management     |
            | Roles          | /admin/roles        | Role Management                      |
            | Scopes         | /admin/scopes       | Scope Management                     |
            | Tenants        | /admin/organisations | Tenant Management                   |

    Scenario: A read-only administrator is only offered what the routes allow
        Given "alice@example.com" holds a role limited to "roles:read" and "scopes:read" and "users:read"
        And "alice@example.com" signed in to the administration console
        Then the sidebar lists "Users"
        And the sidebar lists "Roles"
        And the sidebar lists "Scopes"
        And the sidebar does not list "OAuth2 Clients"
        And the sidebar does not list "JWKS Keys"
        When I open "Scopes" from the sidebar
        Then I should see "Scope Management"
        And I should not see "Create Scope"
        And I should not see "Seed Default Scopes"

    Scenario: The Scopes entry follows the scopes scopes, not the roles scopes
        Given "alice@example.com" holds a role limited to "roles:read" and "users:read"
        And "alice@example.com" signed in to the administration console
        Then the sidebar lists "Roles"
        And the sidebar does not list "Scopes"

    Scenario: An administrator creates a user and finds it in the list
        Given "root@example.com" signed in to the administration console
        And I open "Users" from the sidebar
        When I click "Create User"
        And I fill "Email Address" with "bob@example.com"
        And I fill "Password" with "Sup3r!secret9"
        And I fill "Full Name" with "Bob Builder"
        And I click "Create User"
        Then the URL should contain "/admin/users/"
        And I should see "bob@example.com"
        And the account "bob@example.com" exists and is not verified yet
        When I open "Users" from the sidebar
        And I fill "Search by email" with "bob"
        And I click "Search"
        Then I should see "bob@example.com"
        And I should not see "alice@example.com"

    Scenario: An administrator disables an account and the user can no longer sign in
        Given "root@example.com" signed in to the administration console
        And I open "Users" from the sidebar
        And I click "alice@example.com"
        When I click "Disable User"
        Then the user "alice@example.com" is disabled
        And the page showed a dialog saying "Disable this user?"
        When I click "Enable User"
        Then the user "alice@example.com" is enabled

    Scenario: A password that is too short is refused by the form
        Given "root@example.com" signed in to the administration console
        And I navigate to "/admin/users/create"
        When I fill "Email Address" with "bob@example.com"
        And I fill "Password" with "short"
        And I click "Create User"
        Then no account exists for "bob@example.com"

    Scenario: An administrator defines a scope and cannot define it twice
        Given "root@example.com" signed in to the administration console
        And I open "Scopes" from the sidebar
        When I click "Create Scope"
        And I fill "Scope Name" with "reports:read"
        And I fill "Resource" with "reports"
        And I fill "Action" with "read"
        And I click "Create Scope"
        Then the URL should contain "/admin/scopes/"
        And I should see "reports:read"
        When I navigate to "/admin/scopes/create"
        And I fill "Scope Name" with "reports:read"
        And I fill "Resource" with "reports"
        And I fill "Action" with "read"
        And I click "Create Scope"
        Then the URL should contain "/admin/scopes/create?error="

    Scenario: An administrator creates a role and assigns it to a user
        Given "root@example.com" signed in to the administration console
        And I open "Roles" from the sidebar
        When I click "Create Role"
        And I fill "Role Name" with "auditor"
        And I fill "Description" with "Reads the audit trail"
        And I click "Create Role"
        Then I should see "auditor"
        When I click "Assign User"
        And I fill "search" with "alice"
        And I click "Search"
        And I choose the row of "alice@example.com"
        And I click "Assign Role"
        Then I should see "alice@example.com"
        And the user "alice@example.com" has the role "auditor" in the database

    Scenario: An administrator edits a custom role and cannot edit a system role
        Given "root@example.com" signed in to the administration console
        And I open "Roles" from the sidebar
        When I click "Create Role"
        And I fill "Role Name" with "auditor"
        And I fill "Description" with "Reads the audit trail"
        And I click "Create Role"
        Then I should see "Reads the audit trail"
        When I click "Edit Role"
        Then the URL should contain "/edit"
        When I fill "Description" with "Reads everything"
        And I click "Save Role"
        Then I should see "Role updated successfully"
        And I should see "Reads everything"
        When I open "Roles" from the sidebar
        And I click "console_admin"
        Then I should not see "Edit Role"
        When I navigate to the edit page of the role "console_admin"
        Then I should see "System roles cannot be modified"

    Scenario: An administrator registers an OAuth2 client and sees its secret once
        Given "root@example.com" signed in to the administration console
        And I open "OAuth2 Clients" from the sidebar
        When I click "Create Client"
        And I fill "Client Name" with "Reporting"
        And I fill "Redirect URIs" with "https://reporting.example.com/callback"
        And I click "Create Client"
        Then I should see "Client created successfully"
        And I should see "New Client Secret"
        And the client "Reporting" exists in the database
        And the secret shown on the page is the one of the client "Reporting"
        When I open "OAuth2 Clients" from the sidebar
        Then I should see "Reporting"
        And I should not see "New Client Secret"

    Scenario: An administrator creates a tenant and adds a member from its page
        Given "root@example.com" signed in to the administration console
        And I open "Tenants" from the sidebar
        When I click "Create Tenant"
        And I fill "Display Name" with "Acme Corp"
        And I fill "Slug" with "acme"
        And I click "Create Tenant"
        Then I should see "Tenant Details"
        And I should see "Acme Corp"
        When I click "Add Member"
        And I fill "User Email" with "alice@example.com"
        And I click the button named exactly "Add"
        Then I should see "alice@example.com"
        And the user "alice@example.com" is a member of the tenant "acme"

    Scenario Outline: The customization pages of a tenant open from its page
        Given the tenant "acme" exists
        And "root@example.com" signed in to the administration console
        And I open "Tenants" from the sidebar
        And I click "acme"
        When I click "<link>"
        Then the URL should contain "<path>"
        And I should see "<heading>"
        And the browser should report no errors

        Examples:
            | link                  | path                 | heading             |
            | Branding              | /branding            | Branding            |
            | Templates             | /templates           | Templates           |
            | Profile Fields        | /profile-fields      | Profile Fields      |
            | Registration Fields   | /registration-fields | Registration Fields |
            | Allowed Scopes        | /allowed-scopes      | Allowed Scopes      |

    Scenario: An administrator generates a signing key and publishes it
        Given a signing key store protected by a fresh encryption key
        And "root@example.com" signed in to the administration console
        And I open "JWKS Keys" from the sidebar
        When I click "Generate New Key"
        And I tick the box "Activate immediately"
        And I click "Generate Key"
        Then the URL should contain "/admin/jwks"
        And the published key set lists the key shown on the page

    Scenario: An administrator revokes a session from the sessions page
        Given a session is opened for "alice@example.com"
        And "root@example.com" signed in to the administration console
        And I open "Sessions" from the sidebar
        When I click "Revoke" in the row of "alice@example.com"
        Then the user "alice@example.com" has 0 active sessions
        And the page showed a dialog saying "Revoke this session?"

    Scenario: An identity provider created in the console lets members sign in
        Given the tenant "acme" exists
        And the tenant "acme" has its default roles
        And identity provider secrets are encrypted with a fresh key
        And an external identity provider with the user "bob@example.com" and the password "idp-secret-1"
        And "root@example.com" signed in to the administration console
        And I open "Tenants" from the sidebar
        And I click "acme"
        When I click "Add IdP"
        And I fill "Name" with "Acme SSO"
        And I fill "Client ID" with the client id of the external identity provider
        And I fill "Client Secret" with the client secret of the external identity provider
        And I fill "Discovery URL" with the discovery address of the external identity provider
        And I click "Create Identity Provider"
        Then I should see "Acme SSO"
        Given the tenants of the application are served by path
        When the visitor starts the sign-in with "Acme SSO" for the tenant "acme" returning to "/auth/mfa/status"
        And the visitor signs in at the identity provider
        Then the URL should contain "/auth/mfa/status?state=orig-state"
        And the user "bob@example.com" is a member of the tenant "acme"

    Scenario: An administrator edits the profile of a user
        Given "root@example.com" signed in to the administration console
        And I open "Users" from the sidebar
        And I click "alice@example.com"
        When I click "Edit User"
        And I fill "Display Name / Nickname" with "ally"
        And I fill "First Name" with "Alice"
        And I fill "Last Name" with "Liddell"
        And I click "Save Changes"
        Then I should see "ally"
        And I should see "Alice"

    Scenario: An administrator rotates the secret of a client
        Given a client application "reporting" with the scopes "openid" that skips consent
        And "root@example.com" signed in to the administration console
        And I open "OAuth2 Clients" from the sidebar
        And I click "reporting"
        When I click "Rotate Secret"
        Then I should see "Secret rotated successfully"
        And I should see "New Client Secret"
        And the secret shown on the page is the one of the client "reporting"
        And the page showed a dialog saying "Rotate client secret?"

    Scenario: The access token page explains that there is none yet
        Given "root@example.com" signed in to the administration console
        When I open "Access Tokens" from the sidebar
        Then I should see "No personal access tokens found."
