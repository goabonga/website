@browser
Feature: Multi-factor authentication in a browser
    As a signed-in user
    I want to enrol an authenticator app and to confirm my identity by e-mail from the account pages
    So that a stolen password or session cookie is not enough to take my account over

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And an encryption key is configured
        And the application is served at its public address
        And a verified user "alice@example.com" with the password "Sup3r!secret"

    Scenario: The setup page asks the visitor to sign in first
        When I navigate to "/auth/mfa/setup"
        Then I should see "Please login first"
        And the page title should be "MFA Setup - Auth"

    Scenario: The setup page shows the QR code and the secret of the authenticator app
        Given a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        When I navigate to "/auth/mfa/setup"
        Then I should see "Two-Factor Authentication Setup"
        And the QR code image of the page is displayed
        And the secret shown next to the QR code is the one stored encrypted
        And the page should link "Back to security settings" to "/auth/settings/security"
        And the browser should report no errors

    Scenario: The authenticator app is enrolled with the code it displays
        Given a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        And I navigate to "/auth/mfa/setup"
        When I read the secret shown next to the QR code
        And I enter the current code of the authenticator app in the setup form
        And I click "Verify and Enable"
        Then I should see "Two-factor authentication is now enabled!"
        And the page lists 10 backup codes
        And TOTP is enabled for the user in the database
        And the MFA status shows TOTP enabled with 10 backup codes remaining
        When I answer the challenge with the first backup code
        Then the response status is 200
        And the MFA status shows TOTP enabled with 9 backup codes remaining
        And the browser should report no errors

    Scenario: A wrong code keeps the setup open until the right one is entered
        Given a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        And I navigate to "/auth/mfa/setup"
        And I read the secret shown next to the QR code
        When I fill "Enter the 6-digit code" with "000000"
        And I click "Verify and Enable"
        Then I should see "Invalid code or TOTP not set up"
        And TOTP is disabled for the user in the database
        When I enter the current code of the authenticator app in the setup form
        And I click "Verify and Enable"
        Then I should see "Two-factor authentication is now enabled!"
        And TOTP is enabled for the user in the database

    Scenario: The setup page of a user who enrolled offers to start again
        Given a session is opened for "alice@example.com"
        And TOTP is enabled for the user
        And the browser holds the cookie of the session
        When I navigate to "/auth/mfa/setup"
        Then I should see "Two-factor authentication is already enabled on your account."
        And the TOTP secret is stored encrypted
        When I click "Reconfigure"
        Then the QR code image of the page is displayed
        And the secret shown next to the QR code is the one stored encrypted
        And TOTP is disabled for the user in the database

    Scenario: The e-mail page asks to sign in first
        When I navigate to "/auth/mfa/email"
        Then I should see "Please login first"

    Scenario: A code received by e-mail is entered on the e-mail verification page
        Given a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        And the browser records the pages it visits
        When I navigate to "/auth/mfa/email"
        Then I should see "a***e@example.com"
        And "Enter the 6-digit code" should be hidden
        When I click "Send Verification Code"
        Then I should see "Code sent! Check your email."
        And an MFA e-mail with a 6 digit code was sent to "alice@example.com"
        When I enter the e-mailed MFA code of alice@example.com
        And I click "Verify Code"
        Then the browser visited "/auth/login?success=mfa_verified"

    Scenario: A wrong e-mail code is refused with a message
        Given a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        And the browser records the dialogs of the page
        And I navigate to "/auth/mfa/email"
        And I click "Send Verification Code"
        When I fill "Enter the 6-digit code" with "000000"
        And I click "Verify Code"
        Then the page showed a dialog saying "Invalid or expired code"
        And the URL should contain "/auth/mfa/email"
