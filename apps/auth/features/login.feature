Feature: Login and password reset
    As a registered user
    I want to sign in, to be challenged for my second factor and to recover a lost password
    So that I can reach my account without exposing it

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And an encryption key is configured
        And the test client talks plain HTTP
        And a verified user "alice@example.com" with the password "Sup3r!secret"

    Scenario: The login form is served
        When I send a GET request to "/auth/login"
        Then the response status is 200
        And the response body contains "password"

    Scenario: Signing in through the API opens a session
        When I sign in through the API as "alice@example.com" with the password "Sup3r!secret"
        Then the response status is 200
        And the response JSON field "message" is "Login successful"
        And the response sets an HttpOnly session cookie
        And the session cookie belongs to "alice@example.com"

    Scenario Outline: Wrong credentials are refused
        Given the user "alice@example.com" is <state>
        When I sign in through the API as "<email>" with the password "<password>"
        Then the response status is 401
        And the response JSON field "detail" is "Invalid email or password"

        Examples:
            | state      | email              | password     |
            | verified   | alice@example.com  | wrong        |
            | verified   | nobody@example.com | Sup3r!secret |
            | unverified | alice@example.com  | Sup3r!secret |
            | inactive   | alice@example.com  | Sup3r!secret |

    Scenario: The session of a sign-in can be used to sign out
        Given I signed in through the API as "alice@example.com" with the password "Sup3r!secret"
        When I send a POST request to "/auth/logout/api"
        Then the response status is 200

    Scenario: Signing in through the form redirects to the requested page
        When I submit the login form redirecting to "/auth/mfa/status" for "alice@example.com" with the password "Sup3r!secret"
        Then the response status is 303
        And the browser is redirected to a path starting with "/auth/mfa/status"
        And the response sets an HttpOnly session cookie

    Scenario: The login form reports wrong credentials
        When I submit the login form for "alice@example.com" with the password "wrong"
        Then the response status is 401
        And the response sets no session cookie

    Scenario: A user with TOTP must provide a code through the API
        Given the user "alice@example.com" enabled TOTP
        When I sign in through the API as "alice@example.com" with the password "Sup3r!secret"
        Then the response status is 403
        And the response JSON field "detail" is "MFA required"
        When I sign in through the API as "alice@example.com" using the password "Sup3r!secret" and the code "000000"
        Then the response status is 403
        And the response JSON field "detail" is "Invalid verification code"
        When I sign in through the API as "alice@example.com" using the password "Sup3r!secret" and a valid TOTP code
        Then the response status is 200

    Scenario: The login form asks for the code in a second step
        Given the user "alice@example.com" enabled TOTP
        When I submit the login form redirecting to "/auth/mfa/status" for "alice@example.com" with the password "Sup3r!secret"
        Then the response status is 200
        And the response sets no session cookie
        And the response body contains "otp"
        When I submit the code of the authenticator app
        Then the response status is 303
        And the response sets an HttpOnly session cookie

    Scenario: A lost password is recovered with a single-use link
        When I ask for a password reset for "alice@example.com"
        Then the response status is 200
        And a password reset e-mail was sent to "alice@example.com"
        When I choose the new password "N3w!passphrase" with the e-mailed token
        Then the response status is 200
        And "alice@example.com" can sign in with "N3w!passphrase"
        And "alice@example.com" can no longer sign in with "Sup3r!secret"
        When I choose the new password "An0ther!pass" with the e-mailed token
        Then the response status is 400

    Scenario: Asking for a reset does not reveal which addresses exist
        When I ask for a password reset for "nobody@example.com"
        Then the response status is 200
        And no e-mail was sent to "nobody@example.com"

    Scenario: A weak new password is refused
        When I ask for a password reset for "alice@example.com"
        And I choose the new password "weak" with the e-mailed token
        Then the response status is 422
