Feature: Account and organisation settings pages
    As a signed-in user
    I want self-service pages for my profile, security, tokens and organisations
    So that I can manage my account without an administrator

    Background:
        Given an empty user database
        And an encryption key is configured
        And outgoing e-mails are captured
        And a verified user "alice@example.com" with the password "Sup3r!secret"

    Scenario: The settings root leads to the profile page
        When I open the settings page "/auth/settings"
        Then the browser is redirected to a path starting with "/auth/settings/profile"

    Scenario: Anonymous visitors are sent to the login page
        When I open the settings page "/auth/settings/profile"
        Then the browser is redirected to a path starting with "/auth/login"

    Scenario: A signed-in user sees the settings pages
        Given "alice@example.com" is signed in
        Then the settings page "<path>" is displayed for each of
            | path                           |
            | /auth/settings/profile         |
            | /auth/settings/password        |
            | /auth/settings/security        |
            | /auth/settings/sessions        |
            | /auth/settings/applications    |
            | /auth/settings/emails          |
            | /auth/settings/organisations   |
            | /auth/settings/tokens          |

    Scenario: The profile is read and updated through the JSON endpoint
        Given "alice@example.com" is signed in
        When I send the settings request "PUT" "/auth/settings/profile/api" with the JSON body
            """
            {"nickname": "ally", "given_name": "Alice", "locale": "fr"}
            """
        Then the response status is 200
        When I open the settings page "/auth/settings/profile/api"
        Then the response status is 200
        And the response JSON field "nickname" is "ally"
        And the response JSON field "locale" is "fr"

    Scenario: The password is changed after checking the current one
        Given "alice@example.com" is signed in
        When I send the settings request "PUT" "/auth/settings/password/api" with the JSON body
            """
            {"current_password": "wrong-password", "new_password": "N3w!password"}
            """
        Then the response status is 400
        When I send the settings request "PUT" "/auth/settings/password/api" with the JSON body
            """
            {"current_password": "Sup3r!secret", "new_password": "short"}
            """
        Then the response status is 400
        When I send the settings request "PUT" "/auth/settings/password/api" with the JSON body
            """
            {"current_password": "Sup3r!secret", "new_password": "N3w!password"}
            """
        Then the response status is 200
        And "alice@example.com" can sign in with "N3w!password"

    Scenario: Sessions are listed and revoked
        Given "alice@example.com" is signed in
        And a second session is opened for "alice@example.com"
        When I open the settings page "/auth/settings/sessions/api"
        Then the response status is 200
        And the response lists 2 sessions

    Scenario: A personal access token is created, listed and revoked
        Given "alice@example.com" holds the administrator role
        And a custom scope "pats:read" exists
        And "alice@example.com" is signed in
        When I send the settings request "POST" "/auth/settings/tokens/api" with the JSON body
            """
            {"name": "CI token", "scopes": ["pats:read"], "expiration": "30_days"}
            """
        Then the response status is 201
        And the response carries a new personal access token
        When I open the settings page "/auth/settings/tokens/api"
        Then the response lists the token "CI token"
        When I revoke the personal access token created from the settings
        Then the response status is 200

    Scenario: A token cannot request scopes the user does not hold
        Given "alice@example.com" is signed in
        When I send the settings request "POST" "/auth/settings/tokens/api" with the JSON body
            """
            {"name": "Too much", "scopes": ["users:read"], "expiration": "30_days"}
            """
        Then the response status is 400

    Scenario: A user creates an organisation from the settings
        Given "alice@example.com" holds the administrator role
        And "alice@example.com" is signed in
        When I submit the settings form "/auth/settings/organisations/create" with
            | field             | value     |
            | organization_name | Acme Corp |
        Then the browser is redirected to a path starting with "/auth/settings/"
        And "alice@example.com" is a member of the organisation "acme-corp" with the role "owner"
        When I open the settings page "/auth/settings/organisations"
        Then the response body contains "Acme Corp"

    Scenario: A secondary e-mail address is added
        Given "alice@example.com" is signed in
        When I submit the settings form "/auth/settings/emails/add" with
            | field | value             |
            | email | alice@work.test   |
        Then the browser is redirected to a path starting with "/auth/settings/emails"

    Scenario: A member holding only settings:read views the organisation but cannot change it
        Given "alice@example.com" owns the organisation "acme"
        And a verified user "bob@example.com" with the password "Sup3r!secret"
        And the organisation "acme" has a role "viewer" granting "settings:read"
        And "bob@example.com" is a member of the organisation "acme" with the role "viewer"
        And "bob@example.com" is signed in
        When I open the page "/edit" of the organisation "acme" settings
        Then the response status is 200
        When I submit the form "/edit" of the organisation "acme" settings with
            | field        | value   |
            | display_name | Renamed |
        Then the response status is 403
        When I submit the form "/email-sender" of the organisation "acme" settings with
            | field                | value            |
            | email_sender_address | no@reply.example |
        Then the response status is 403
        When I submit the form "/branding" of the organisation "acme" settings with
            | field         | value   |
            | primary_color | #112233 |
        Then the response status is 403
        When I submit the form "/members/add" of the organisation "acme" settings with
            | field | value             |
            | email | alice@example.com |
        Then the response status is 403
        And the organisation "acme" is named "Acme"

    Scenario: A member holding the scope of the operation changes the organisation
        Given "alice@example.com" owns the organisation "acme"
        And a verified user "bob@example.com" with the password "Sup3r!secret"
        And the organisation "acme" has a role "editor" granting "settings:read settings:write"
        And "bob@example.com" is a member of the organisation "acme" with the role "editor"
        And "bob@example.com" is signed in
        When I submit the form "/edit" of the organisation "acme" settings with
            | field        | value   |
            | display_name | Renamed |
        Then the browser is redirected to a path starting with "/auth/settings/org/"
        And the organisation "acme" is named "Renamed"

    Scenario: An organisation admin manages identity providers but not the organisation settings
        Given "alice@example.com" owns the organisation "acme"
        And a verified user "bob@example.com" with the password "Sup3r!secret"
        And "bob@example.com" is a member of the organisation "acme" with the role "admin"
        And "bob@example.com" is signed in
        When I open the page "/idp/create" of the organisation "acme" settings
        Then the response status is 200
        When I submit the form "/edit" of the organisation "acme" settings with
            | field        | value   |
            | display_name | Renamed |
        Then the response status is 403
        And the organisation "acme" is named "Acme"

    Scenario: A member is only offered the controls of the scopes they hold
        Given "alice@example.com" owns the organisation "acme"
        And a verified user "bob@example.com" with the password "Sup3r!secret"
        And the organisation "acme" has a role "viewer" granting "settings:read members:read"
        And "bob@example.com" is a member of the organisation "acme" with the role "viewer"
        And "bob@example.com" is signed in
        When I open the overview of the organisation "acme" settings
        Then the response status is 200
        And the response body contains "Organization Details"
        And the response body does not contain "/members/add"
        And the response body does not contain "/idp/create"
        And the response body does not contain "/roles/create"
        And the response body does not contain "/trust/mode"
        And the response body does not contain "/edit"
        When I open the page "/branding" of the organisation "acme" settings
        Then the response status is 403

    Scenario: A member sees the controls of the scopes of their role and no other
        Given "alice@example.com" owns the organisation "acme"
        And a verified user "bob@example.com" with the password "Sup3r!secret"
        And the organisation "acme" has a role "manager" granting "settings:read members:invite idp:*"
        And "bob@example.com" is a member of the organisation "acme" with the role "manager"
        And "bob@example.com" is signed in
        When I open the overview of the organisation "acme" settings
        Then the response body contains "/members/add"
        And the response body contains "/idp/create"
        And the response body does not contain "/update-role"
        And the response body does not contain "/trust/mode"
        And the response body does not contain "/webhooks/create"

    Scenario: The custom domain has its own scope, settings:write does not change it
        Given the custom domain tasks are not sent to a broker
        And "alice@example.com" owns the organisation "acme"
        And a verified user "bob@example.com" with the password "Sup3r!secret"
        And the organisation "acme" has a role "editor" granting "settings:read settings:write"
        And "bob@example.com" is a member of the organisation "acme" with the role "editor"
        And "bob@example.com" is signed in
        When I open the page "/edit" of the organisation "acme" settings
        Then the response status is 200
        And the response body does not contain "custom_domain"
        When I submit the form "/edit" of the organisation "acme" settings with
            | field         | value             |
            | display_name  | Renamed           |
            | custom_domain | evil.example.com  |
        Then the organisation "acme" is named "Renamed"
        And the organisation "acme" has no custom domain
        When I submit the form "/domain" of the organisation "acme" settings with
            | field         | value             |
            | custom_domain | evil.example.com  |
        Then the response status is 403
        And the organisation "acme" has no custom domain
        And no custom domain task is queued

    Scenario: A member holding domain:write sets and removes the custom domain
        Given the custom domain tasks are not sent to a broker
        And "alice@example.com" owns the organisation "acme"
        And a verified user "bob@example.com" with the password "Sup3r!secret"
        And the organisation "acme" has a role "domains" granting "settings:read domain:read domain:write"
        And "bob@example.com" is a member of the organisation "acme" with the role "domains"
        And "bob@example.com" is signed in
        When I open the page "/edit" of the organisation "acme" settings
        Then the response body contains "custom_domain"
        When I submit the form "/domain" of the organisation "acme" settings with
            | field         | value              |
            | custom_domain | auth.acme.example  |
        Then the browser is redirected to a path starting with "/auth/settings/org/"
        And the organisation "acme" has the custom domain "auth.acme.example"
        And the DNS verification of the custom domain is queued
        When I submit the form "/edit" of the organisation "acme" settings with
            | field        | value   |
            | display_name | Renamed |
        Then the response status is 403
        When I open the page "/domain-status" of the organisation "acme" settings
        Then the response status is 200
        And the response JSON field "custom_domain" is "auth.acme.example"

    Scenario: The owner of an organisation sets the custom domain
        Given the custom domain tasks are not sent to a broker
        And "alice@example.com" owns the organisation "acme"
        And "alice@example.com" is signed in
        When I submit the form "/domain" of the organisation "acme" settings with
            | field         | value              |
            | custom_domain | auth.acme.example  |
        Then the organisation "acme" has the custom domain "auth.acme.example"
        When I submit the form "/domain" of the organisation "acme" settings with
            | field         | value |
            | custom_domain |       |
        Then the organisation "acme" has no custom domain
