Feature: Administration console
    As a platform administrator
    I want server-rendered pages to manage the service
    So that I can operate users, scopes, organisations and signing keys from a browser

    Background:
        Given an empty user database
        And a verified user "root@example.com" with the password "Sup3r!secret"
        And a verified user "alice@example.com" with the password "Sup3r!secret"
        And "root@example.com" holds the administrator role

    Scenario: Anonymous visitors are not served
        When I open the admin page "/admin/"
        Then the response status is 303

    Scenario: A user without an administrator role is refused
        Given an administrator session for "alice@example.com"
        When I open the admin page "/admin/"
        Then the response status is 403

    Scenario: The dashboard shows aggregate counters
        Given an administrator session for "root@example.com"
        When I open the admin page "/admin/"
        Then the response status is 200
        And the response body contains "Dashboard"

    Scenario: The user list and detail pages show accounts
        Given an encryption key is configured
        And an administrator session for "root@example.com"
        When I open the admin page "/admin/users"
        Then the response status is 200
        And the response body contains "User Management"
        And the response body contains "alice@example.com"
        When I open the detail page of the user "alice@example.com"
        Then the response status is 200
        And the response body contains "alice@example.com"

    Scenario: An administrator creates a user from the form
        Given an administrator session for "root@example.com"
        When I submit the admin form "/admin/users/create" with
            | field    | value             |
            | email    | bob@example.com   |
            | password | Sup3r!secret9     |
        Then the browser is redirected to a path starting with "/admin/users/"
        And the account "bob@example.com" exists and is not verified yet

    Scenario: A password that is too short is refused by the form
        Given an administrator session for "root@example.com"
        When I submit the admin form "/admin/users/create" with
            | field    | value             |
            | email    | bob@example.com  |
            | password | short             |
        Then the browser is redirected to a path starting with "/admin/users/create?error="
        And no account exists for "bob@example.com"

    Scenario: An administrator disables and enables an account
        Given an administrator session for "root@example.com"
        When I post to the admin action "disable" of the user "alice@example.com"
        Then the user "alice@example.com" is disabled
        When I post to the admin action "enable" of the user "alice@example.com"
        Then the user "alice@example.com" is enabled

    Scenario: An administrator defines a scope and cannot duplicate it
        Given an administrator session for "root@example.com"
        When I submit the admin form "/admin/scopes/create" with
            | field    | value         |
            | name     | reports:read  |
            | resource | reports       |
            | action   | read          |
        Then the browser is redirected to a path starting with "/admin/scopes/"
        When I submit the admin form "/admin/scopes/create" with
            | field    | value         |
            | name     | reports:read  |
            | resource | reports       |
            | action   | read          |
        Then the browser is redirected to a path starting with "/admin/scopes/create?error="

    Scenario: An administrator creates an organisation
        Given an administrator session for "root@example.com"
        When I submit the admin form "/admin/organisations/create" with
            | field        | value  |
            | slug         | acme   |
            | display_name | Acme   |
        Then the browser is redirected to a path starting with "/admin/organisations/"
        When I open the admin page "/admin/organisations"
        Then the response body contains "acme"

    Scenario: The signing key pages are reachable
        Given an encryption key is configured
        And an administrator session for "root@example.com"
        When I open the admin page "/admin/jwks"
        Then the response status is 200

    Scenario: A read-only role is not offered the actions it would be refused
        Given "alice@example.com" holds a role limited to "scopes:read" and "users:read"
        And an administrator session for "alice@example.com"
        When I open the admin page "/admin/scopes"
        Then the response status is 200
        And the response body contains "Scope Management"
        And the response body does not contain "/admin/scopes/create"
        And the response body does not contain "/admin/scopes/seed"
        When I submit the admin form "/admin/scopes/create" with
            | field    | value         |
            | name     | reports:read  |
            | resource | reports       |
            | action   | read          |
        Then the response status is 403
        When I open the admin page "/admin/"
        Then the response body contains "Manage Users"
        And the response body does not contain "Manage Roles"
        And the response body does not contain "Manage Clients"

    Scenario: The role that holds the scope is offered the action
        Given "alice@example.com" holds a role limited to "scopes:read" and "scopes:write"
        And an administrator session for "alice@example.com"
        When I open the admin page "/admin/scopes"
        Then the response status is 200
        And the response body contains "/admin/scopes/create"
        And the response body contains "/admin/scopes/seed"

    Scenario: The scopes pages follow the scopes scopes, not the roles scopes
        Given "alice@example.com" holds a role limited to "roles:read" and "roles:write"
        And an administrator session for "alice@example.com"
        When I open the admin page "/admin/scopes"
        Then the response status is 403
        When I open the admin page "/admin/roles"
        Then the response status is 200
        And the response body does not contain "/admin/scopes"

    Scenario: An administrator edits the description and the scopes of a custom role
        Given the scope "users:read" exists
        And the scope "users:write" exists
        And a custom role "editor" holds the scopes "users:read"
        And an administrator session for "root@example.com"
        When I open the edit page of the role "editor"
        Then the response status is 200
        And the response body contains "Save Role"
        When I submit the edit form of the role "editor" with
            | field       | value             |
            | description | Edits the users   |
            | scopes      | users:write       |
        Then the browser is redirected to a path starting with "/admin/roles/"
        And the role "editor" holds exactly the scopes "users:write"
        When I submit the edit form of the role "editor" with
            | field  | value        |
            | scopes | nope:nothing |
        Then the browser is redirected to a path starting with "/admin/roles/"
        And the role "editor" holds exactly the scopes "users:write"

    Scenario: A system role cannot be edited
        Given an administrator session for "root@example.com"
        When I open the edit page of the role "console_admin"
        Then the browser is redirected to a path starting with "/admin/roles/"

    Scenario: Editing a role needs the roles:write scope
        Given a custom role "editor" holds the scopes "users:read"
        And "alice@example.com" holds a role limited to "roles:read"
        And an administrator session for "alice@example.com"
        When I open the edit page of the role "editor"
        Then the response status is 403
