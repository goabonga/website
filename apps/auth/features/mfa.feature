Feature: Multi-factor authentication
    As a signed-in user
    I want a second factor on my account
    So that a stolen password or session cookie is not enough to take it over

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And an encryption key is configured
        And a verified user "alice@example.com" with the password "Sup3r!secret"
        And a session is opened for "alice@example.com"

    Scenario: MFA endpoints require a session
        When I send a POST request to "/auth/mfa/totp/setup"
        Then the response status is 401

    Scenario: A user without MFA has no backup codes
        When I request "/auth/mfa/status" with the session cookie
        Then the response status is 200
        And the response JSON field "totp_enabled" is "False"

    Scenario: Enrolling an authenticator app
        When I start the TOTP enrolment
        Then the response status is 200
        And the response provides a secret and a QR code image
        And the TOTP secret is stored encrypted
        When I confirm the enrolment with a valid code
        Then the response status is 200
        And 10 backup codes are returned
        And the MFA status shows TOTP enabled with 10 backup codes remaining

    Scenario: A wrong code does not enable TOTP
        Given I started the TOTP enrolment
        When I confirm the enrolment with the code "000000"
        Then the response status is 400
        And the MFA status shows TOTP disabled

    Scenario: A user who enabled TOTP cannot enrol twice
        Given TOTP is enabled for the user
        When I start the TOTP enrolment
        Then the response status is 400

    Scenario: A TOTP code passes the challenge
        Given TOTP is enabled for the user
        When I answer the challenge with a valid TOTP code
        Then the response status is 200
        When I answer the challenge with the code "000000"
        Then the response status is 400

    Scenario: A backup code can be used only once
        Given TOTP is enabled for the user
        When I answer the challenge with the first backup code
        Then the response status is 200
        And the MFA status shows TOTP enabled with 9 backup codes remaining
        When I answer the challenge with the first backup code
        Then the response status is 400

    Scenario: Backup codes can be regenerated
        Given TOTP is enabled for the user
        When I regenerate the backup codes
        Then the response status is 200
        And 10 backup codes are returned
        And the previous backup codes no longer work

    Scenario: Disabling TOTP needs a valid code
        Given TOTP is enabled for the user
        When I disable TOTP with the code "000000"
        Then the response status is 400
        When I disable TOTP with a valid code
        Then the response status is 200
        And the MFA status shows TOTP disabled

    Scenario: An e-mail code can be used as a second factor
        When I ask for an MFA code by e-mail
        Then the response status is 200
        And the response JSON field "email_masked" is "a***e@example.com"
        And an MFA e-mail with a 6 digit code was sent to "alice@example.com"
        When I submit the e-mailed MFA code
        Then the response status is 200
        When I submit the e-mailed MFA code
        Then the response status is 400
