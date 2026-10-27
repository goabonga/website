@browser
Feature: Account and organisation settings in a browser
    As a signed-in user
    I want to manage my profile, my security, my tokens and my organisations from the settings pages
    So that I can look after my account without an administrator

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And an encryption key is configured
        And the application is served at its public address
        And a verified user "alice@example.com" with the password "Sup3r!secret"
        And the browser records the dialogs of the page

    Scenario: Anonymous visitors are sent to the login page and come back after signing in
        When I navigate to "/auth/settings/profile"
        Then the URL should contain "/auth/login"
        When I sign in as "alice@example.com" with the password "Sup3r!secret"
        Then the URL should be "/auth/settings/profile"
        And I should see "Profile"

    Scenario Outline: Every page of the settings menu opens
        Given "alice@example.com" signed in to the settings
        When I open "<section>" from the settings menu
        Then the URL should contain "<path>"
        And I should see "<heading>"
        And the settings menu marks "<section>" as the current section
        And the browser should report no errors

        Examples:
            | section        | path                         | heading                |
            | Profile        | /auth/settings/profile       | Profile                |
            | Emails         | /auth/settings/emails        | Email Addresses        |
            | Password       | /auth/settings/password      | Change Password        |
            | Security       | /auth/settings/security      | Security               |
            | Sessions       | /auth/settings/sessions      | Active Sessions        |
            | Applications   | /auth/settings/applications  | Connected Applications |
            | Personal Tokens | /auth/settings/tokens       | Personal Access Tokens |
            | Organizations  | /auth/settings/organisations | Organizations          |

    Scenario: The profile is updated from the profile page
        Given "alice@example.com" signed in to the settings
        When I fill "Display name" with "ally"
        And I fill "First name" with "Alice"
        And I fill "Last name" with "Liddell"
        And I click "Save changes"
        Then I should see "Profile updated successfully"
        And the field "Display name" should have the value "ally"
        And the stored profile of "alice@example.com" has nickname "ally"
        And the stored profile of "alice@example.com" has given name "Alice"

    Scenario: A profile picture is uploaded from the profile page
        Given "alice@example.com" signed in to the settings
        When I choose the avatar file "alice.png" on the profile page
        And I click "Upload"
        Then the profile picture of "alice@example.com" is stored under the uploads

    Scenario: The password is changed after checking the current one
        Given "alice@example.com" signed in to the settings
        And I open "Password" from the settings menu
        When I fill "Current password" with "wrong-password"
        And I fill "New password" with "N3w!password"
        And I fill "Confirm new password" with "N3w!password"
        And I click "Update password"
        Then I should see "Current password is incorrect"
        When I fill "Current password" with "Sup3r!secret"
        And I fill "New password" with "N3w!password"
        And I fill "Confirm new password" with "Other!password1"
        And I click "Update password"
        Then I should see "do not match"
        When I fill "Current password" with "Sup3r!secret"
        And I fill "New password" with "N3w!password"
        And I fill "Confirm new password" with "N3w!password"
        And I click "Update password"
        Then I should see "Password changed successfully."
        And "alice@example.com" can sign in with "N3w!password"
        And "alice@example.com" can no longer sign in with "Sup3r!secret"

    Scenario: A new e-mail address is verified with the code received, then made primary
        Given "alice@example.com" signed in to the settings
        And I open "Emails" from the settings menu
        When I fill "Email address" with "ally@example.com"
        And I click "Add email"
        Then I should see "ally@example.com"
        And I should see "Not verified"
        When I enter the e-mailed code of "ally@example.com" on the e-mails page
        And I click "Verify"
        Then I should see "Verified"
        When I click "Set as primary"
        Then I should see "Primary email updated successfully"

    Scenario: An e-mail address that is not primary can be removed after a confirmation
        Given the user "alice@example.com" also has the verified address "ally@example.com"
        And "alice@example.com" signed in to the settings
        And I open "Emails" from the settings menu
        When I click "Remove"
        Then the page showed a dialog saying "Remove this email"
        And I should not see "ally@example.com"

    Scenario: Two-factor authentication is enabled, its backup codes regenerated and then disabled
        Given an encryption key is configured
        And "alice@example.com" signed in to the settings
        And I open "Security" from the settings menu
        Then I should see "Disabled"
        When I click the link named exactly "Enable"
        And I read the secret shown next to the QR code
        And I enter the current code of the authenticator app in the setup form
        And I click "Verify and Enable"
        Then the page lists 10 backup codes
        When I navigate to "/auth/settings/security"
        Then I should see "10"
        And I should see "codes remaining"
        When I enter "000000" in the regenerate form
        And I click "Regenerate backup codes"
        Then I should see "Invalid"
        When I enter the current authenticator code in the regenerate form
        And I click "Regenerate backup codes"
        Then I should see "New backup codes generated"
        And the security page lists 10 new backup codes
        When I enter the current authenticator code in the disable form
        And I click the button named exactly "Disable 2FA"
        Then I should see "Disabled"
        And TOTP is disabled for the user in the database

    Scenario: Another session is revoked from the sessions page
        Given "alice@example.com" signed in to the settings
        And a second session is opened for "alice@example.com"
        And I open "Sessions" from the settings menu
        Then I should see "Current"
        And I should see "Revoke all other sessions"
        When I click the button named exactly "Revoke"
        Then the user "alice@example.com" has 1 active sessions
        And I should not see "Revoke all other sessions"

    Scenario: Revoking every other session keeps the current one
        Given "alice@example.com" signed in to the settings
        And a second session is opened for "alice@example.com"
        And a second session is opened for "alice@example.com"
        And I open "Sessions" from the settings menu
        When I click "Revoke all other sessions"
        Then the user "alice@example.com" has 1 active sessions
        And the session cookie of the browser belongs to "alice@example.com"

    Scenario: An application that was granted access is listed and can be revoked
        Given a signing key store protected by a fresh encryption key
        And the operator generated and activated a signing key
        And the platform tenant "platform" exists
        And a client application "spa" with the scopes "openid email" that requires consent
        And "alice@example.com" signed in to the settings
        When the browser opens the authorization request of "spa" for the scopes "openid email"
        And I click "Allow"
        Then the callback page of the client application received a code and the state sent
        When the client application redeems the code of the callback page
        Then the response status is 200
        When I navigate to "/auth/settings/applications"
        Then I should see "spa"
        And I should see "openid, email"
        When I click "Revoke"
        Then I should see "You haven't authorized any third-party applications yet."
        When the client refreshes the tokens
        Then the response status is 400

    Scenario: A personal access token is created, used against the API and revoked
        Given "alice@example.com" holds a role granting the scopes "users:read"
        And "alice@example.com" signed in to the settings
        And I open "Personal Tokens" from the settings menu
        When I click "Create new token"
        And I fill "Token name" with "CI pipeline"
        And I tick the scope "users:read" of the new token
        And I click the button named exactly "Create token"
        Then I should see "Your new personal access token"
        And the token shown on the page starts with the personal access token prefix
        And the token shown on the page opens the users API
        When I click "Done"
        Then I should see "CI pipeline"
        And I should see "users:read"
        When I click "Revoke"
        Then the page showed a dialog saying "want to revoke"
        And the token of the page no longer opens the users API

    Scenario: A user allowed to create organizations creates one and becomes its owner
        Given "alice@example.com" holds a role granting the scopes "org:write"
        And "alice@example.com" signed in to the settings
        And I open "Organizations" from the settings menu
        When I fill "Organization name" with "Acme Corp"
        And I click "Create"
        Then I should see "created successfully"
        When I click "Manage"
        Then I should see "Organization Details"
        And I should see "Acme Corp"
        And the user "alice@example.com" is a member of the tenant "acme-corp"

    Scenario: An owner renames the organization and sets the sender of its e-mails
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And "alice@example.com" signed in to the settings
        And I open the organization "Acme Corp" from the organizations page
        When I click "Edit"
        And I fill "Organization Name" with "Acme Corporation"
        And I click "Save Changes"
        Then I should see "Organization updated successfully"
        And I should see "Acme Corporation"
        When I click "Edit"
        And I fill "Sender Email Address" with "no-reply@acme.example"
        And I fill "Sender Display Name" with "Acme Accounts"
        And I click "Save Sender"
        Then the field "Sender Email Address" should have the value "no-reply@acme.example"
        And the field "Sender Display Name" should have the value "Acme Accounts"

    Scenario: A member only sees the controls of the scopes of their role
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And a verified user "bob@example.com" with the password "Sup3r!secret"
        And the organisation "acme" has a role "support" granting "settings:read members:read webhooks:read"
        And "bob@example.com" is a member of the organisation "acme" with the role "support"
        And "bob@example.com" signed in to the settings
        When I open the organization "Acme Corp" from the organizations page
        Then I should see "Organization Details"
        And I should see "Members (2)"
        And I should see "Webhooks (0)"
        And I should not see "Edit Info"
        And I should not see "Add Member"
        And I should not see "Manage Roles"
        And I should not see "Create Role"
        And I should not see "Add IdP"
        And I should not see "Update Trust Mode"
        And I should not see "Colors, logos, fonts, and custom CSS/JS"
        And I should not see "Create and manage OAuth2 client applications"
        And I should not see "Add Webhook"

    Scenario: A member allowed to rename the organization does not see its custom domain
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And a verified user "bob@example.com" with the password "Sup3r!secret"
        And the organisation "acme" has a role "editor" granting "settings:read settings:write"
        And "bob@example.com" is a member of the organisation "acme" with the role "editor"
        And "bob@example.com" signed in to the settings
        And I open the organization "Acme Corp" from the organizations page
        When I click "Edit"
        Then I should see "Email Sender"
        And I should not see "Custom Domain"
        When I fill "Organization Name" with "Acme Corporation"
        And I click "Save Changes"
        Then I should see "Organization updated successfully"
        And I should see "Acme Corporation"

    Scenario: A member holding domain:write sets the custom domain and cannot rename the organization
        Given the custom domain tasks are not sent to a broker
        And "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And a verified user "bob@example.com" with the password "Sup3r!secret"
        And the organisation "acme" has a role "domains" granting "settings:read domain:read domain:write"
        And "bob@example.com" is a member of the organisation "acme" with the role "domains"
        And "bob@example.com" signed in to the settings
        And I open the organization "Acme Corp" from the organizations page
        When I click "Edit"
        Then I should see "Custom Domain"
        And I should not see "Save Changes"
        And I should not see "Email Sender"
        When I fill "Custom Domain" with "auth.acme.example"
        And I click "Save Domain"
        Then I should see "Custom domain updated"
        And I should see "Domain Status"
        And the organisation "acme" has the custom domain "auth.acme.example"

    Scenario: An owner adds a member, changes the role and removes the member
        Given a verified user "bob@example.com" with the password "Sup3r!secret"
        And "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And "alice@example.com" signed in to the settings
        And I open the organization "Acme Corp" from the organizations page
        When I click "Add Member"
        And I fill "User Email" with "bob@example.com"
        And I click the button named exactly "Add"
        Then I should see "bob@example.com"
        And the user "bob@example.com" is a member of the tenant "acme"
        When I click "Remove" in the row of "bob@example.com"
        Then the page showed a dialog saying "Remove"
        And I should not see "bob@example.com"

    Scenario: An owner defines a custom role with permissions
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And "alice@example.com" signed in to the settings
        And I open the organization "Acme Corp" from the organizations page
        When I click "Manage Roles"
        And I click "Create Role"
        And I fill "Role Name" with "auditor"
        And I fill "Display Name" with "Auditor"
        And I fill "Description" with "Reads the audit trail"
        And I click "Create Role"
        Then I should see "Auditor"
        And the tenant "acme" has a role "auditor"

    Scenario: The registration fields chosen by an owner change the registration page of the organization
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And the tenants of the application are served by path
        And "alice@example.com" signed in to the settings
        And I open "/t/acme/auth/register" on the tenants server
        Then the page asks for "Phone Number"
        And the page asks for "Street Address"
        When I open the organization "Acme Corp" from the organizations page
        And I click "Registration Fields"
        And I untick "Phone Number"
        And I untick "Address"
        And I click "Save Configuration"
        Then I should see "Registration fields updated"
        When I open "/t/acme/auth/register" on the tenants server
        Then the page does not ask for "Phone Number"
        And the page does not ask for "Street Address"
        And the page asks for "Nickname"

    Scenario: The colours chosen by an owner brand the login page of the organization
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And the tenants of the application are served by path
        And "alice@example.com" signed in to the settings
        And I open the organization "Acme Corp" from the organizations page
        When I click "Branding"
        And I set the colour field "primary_color" to "#aa0000"
        And I click "Save Branding"
        Then I should see "Branding updated"
        When I open "/t/acme/auth/register" on the tenants server
        Then the submit button of the page is outlined in "#aa0000"

    Scenario: A member links the identity provider of the organization and can unlink it
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And identity provider secrets are encrypted with a fresh key
        And an external identity provider with the user "alice@example.com" and the password "idp-secret-1"
        And the tenant "acme" trusts the external identity provider as "Acme SSO"
        And the tenants of the application are served by path
        And "alice@example.com" signed in to the settings
        When I open "/auth/settings/organisations" on the tenants server
        Then I should see "Link Additional Providers"
        When I click "Link Acme SSO"
        Then the browser is at the identity provider
        When the visitor signs in at the identity provider
        Then the URL should contain "/auth/settings/organisations"
        And I should see "Acme SSO"
        And I should see "alice@example.com"
        And the user has 1 federated identity
        When I click "Unlink"
        Then the page showed a dialog saying "Unlink this identity provider?"
        And the user has 0 federated identity

    Scenario: An owner registers an OAuth2 client for the organization and sees its secret once
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And "alice@example.com" signed in to the settings
        And I open the organization "Acme Corp" from the organizations page
        When I click "OAuth2 Clients"
        And I click "Create Client"
        And I fill "Client Name" with "Portal"
        And I fill "Redirect URIs" with "https://portal.example.com/callback"
        And I click the button named exactly "Create Client"
        Then I should see "Portal"
        And I should see "Client Secret (copy now"
        And the client "Portal" exists in the database
        And the secret shown in the warning is the one of the client "Portal"

    Scenario: An owner subscribes a webhook and sends it a signed test event
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And a webhook receiver is listening and private networks are allowed
        And "alice@example.com" signed in to the settings
        And I open the organization "Acme Corp" from the organizations page
        When I click "Add Webhook"
        And I fill "Name" with "Audit"
        And I fill "Target URL" with the address of the webhook receiver
        And I tick the box "every event"
        And I click "Create Webhook"
        Then the signing secret of the webhook is shown
        When I click the button named exactly "Ping"
        Then I should see "Test delivery sent"
        And the receiver was called with a "webhook.test" event signed with that secret

    Scenario: An owner changes the trust policy of the organization
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And "alice@example.com" signed in to the settings
        And I open the organization "Acme Corp" from the organizations page
        When I tick the trust mode "members_only"
        And I click "Update Trust Mode"
        Then I should see "Trust mode updated"

    Scenario: A member leaves an organization after a confirmation
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And a verified user "bob@example.com" with the password "Sup3r!secret"
        And "bob@example.com" is a member of the organization "acme"
        And "bob@example.com" signed in to the settings
        When I open "Organizations" from the settings menu
        And I click "Leave Organization"
        Then the page showed a dialog saying "Leave this organization"
        And the user "bob@example.com" is no longer a member of the tenant "acme"

    Scenario: The profile fields chosen by an owner change the profile page of the members
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And the tenants of the application are served by path
        And "alice@example.com" signed in to the settings
        When I open the organization "Acme Corp" from the organizations page
        And I click "Profile Fields"
        And I untick "Phone number"
        And I click "Save Configuration"
        Then I should see "Profile fields updated"
        When I open "/t/acme/auth/login?next=/t/acme/auth/settings/profile" on the tenants server
        And I sign in as "alice@example.com" with the password "Sup3r!secret"
        Then the URL should contain "/t/acme/auth/settings/profile"
        And the page does not ask for "Phone number"
        And the page asks for "Display name"

    Scenario: An owner adds an identity provider to the organization and pauses it
        Given "alice@example.com" is the owner of the organization "Acme Corp" with the slug "acme"
        And "alice@example.com" signed in to the settings
        And I open the organization "Acme Corp" from the organizations page
        When I click "Add IdP"
        And I fill "Name" with "Acme SSO"
        And I fill "Client ID" with "acme-client"
        And I fill "Client Secret" with "acme-secret"
        And I fill "Discovery URL" with "https://idp.example.org/.well-known/openid-configuration"
        And I click "Create Identity Provider"
        Then I should see "Acme SSO"
        When I click "Disable"
        Then the identity provider "Acme SSO" is switched off in the database
        When I click "Enable"
        Then the identity provider "Acme SSO" is active in the database
