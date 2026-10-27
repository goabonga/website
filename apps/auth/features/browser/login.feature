@browser
Feature: Login and password reset in a browser
    As a registered user
    I want to sign in from the login page, to answer the second factor and to recover a lost password
    So that I can reach my account without exposing it

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And an encryption key is configured
        And the application is served at its public address
        And a verified user "alice@example.com" with the password "Sup3r!secret"

    Scenario: The login page offers the form, the recovery and the registration links
        When I navigate to "/auth/login"
        Then the page title should be "Login - Auth"
        And "Email" should be visible
        And "Password" should be visible
        And the page should link "Forgot your password?" to "/auth/forgot-password"
        And the page should link "Register" to "/auth/register"
        And the browser should report no errors

    Scenario: Signing in opens a session and goes to the requested page
        Given I am on the login page asking to continue to "/auth/mfa/status"
        When I sign in as "alice@example.com" with the password "Sup3r!secret"
        Then the URL should contain "/auth/mfa/status"
        And the session cookie of the browser belongs to "alice@example.com"
        And the session cookie of the browser is HttpOnly, Secure and SameSite Lax
        And the session cookie expires in about 7 days
        And the CSRF cookie of the browser can be read by the scripts of the page
        And the scripts of the page cannot read the session cookie

    Scenario Outline: Wrong credentials are refused on the login page
        Given the user "alice@example.com" is <state>
        And I navigate to "/auth/login"
        When I sign in as "<email>" with the password "<password>"
        Then I should see "Invalid email or password"
        And the URL should contain "/auth/login"
        And the field "Email" should have the value "<email>"
        And the browser holds no session cookie

        Examples:
            | state      | email              | password     |
            | verified   | alice@example.com  | wrong        |
            | verified   | nobody@example.com | Sup3r!secret |
            | unverified | alice@example.com  | Sup3r!secret |
            | inactive   | alice@example.com  | Sup3r!secret |

    Scenario: A user who is already signed in is sent on without seeing the form
        Given the browser holds the cookie of the session of "alice@example.com"
        When I navigate to "/auth/login?next=/auth/mfa/status"
        Then the URL should contain "/auth/mfa/status"

    Scenario: Only a page of the application can be the destination of a sign-in
        Given I am on the login page asking to continue to "//other.invalid/landing"
        When I sign in as "alice@example.com" with the password "Sup3r!secret"
        Then the browser stays on the server of the application
        And the session cookie of the browser belongs to "alice@example.com"

    Scenario: The second factor is asked in a second step
        Given the user "alice@example.com" enabled TOTP
        And I am on the login page asking to continue to "/auth/mfa/status"
        When I sign in as "alice@example.com" with the password "Sup3r!secret"
        Then I should see "Password verified. Enter your authenticator code to continue."
        And "Authenticator code" should be visible
        And the browser holds no session cookie
        When I enter the authenticator code "000000"
        Then I should see "Invalid verification code."
        And the browser holds no session cookie
        When I enter the current code of the authenticator app
        Then the URL should contain "/auth/mfa/status"
        And the session cookie of the browser belongs to "alice@example.com"

    Scenario: A backup code answers the second factor once
        Given the user "alice@example.com" enabled TOTP
        And I navigate to "/auth/login"
        And I sign in as "alice@example.com" with the password "Sup3r!secret"
        When I enter the first backup code
        Then the session cookie of the browser belongs to "alice@example.com"

    Scenario: The second factor can be received by e-mail
        Given the user "alice@example.com" enabled TOTP
        And I navigate to "/auth/login"
        And I sign in as "alice@example.com" with the password "Sup3r!secret"
        When I click "Send a code by email"
        Then I should see "Verification code sent to"
        When I enter the code received by e-mail by alice@example.com
        Then the session cookie of the browser belongs to "alice@example.com"

    Scenario: A lost password is recovered with a single-use link
        Given I navigate to "/auth/login"
        When I click "Forgot your password?"
        Then the URL should contain "/auth/forgot-password"
        When I fill "Email" with "alice@example.com"
        And I click "Send Reset Link"
        Then I should see "If an account exists with this email, a password reset link has been sent."
        And a password reset e-mail was sent to "alice@example.com"
        When I open the password reset link e-mailed to "alice@example.com"
        And I fill "New Password" with "N3w!passphrase"
        And I fill "Confirm Password" with "N3w!passphrase"
        And I click "Reset Password"
        Then the URL should contain "/auth/login?reset=1"
        And I should see "Password reset successfully. You can now log in."
        When I sign in as "alice@example.com" with the password "N3w!passphrase"
        Then the session cookie of the browser belongs to "alice@example.com"
        When I open the password reset link e-mailed to "alice@example.com"
        Then I should see "Invalid or expired reset token"

    Scenario: The old password stops working after a reset
        Given I navigate to "/auth/forgot-password"
        And I fill "Email" with "alice@example.com"
        And I click "Send Reset Link"
        And I open the password reset link e-mailed to "alice@example.com"
        And I fill "New Password" with "N3w!passphrase"
        And I fill "Confirm Password" with "N3w!passphrase"
        And I click "Reset Password"
        When I sign in as "alice@example.com" with the password "Sup3r!secret"
        Then I should see "Invalid email or password"

    Scenario: A reset form refuses a wrong confirmation or a weak password
        Given I navigate to "/auth/forgot-password"
        And I fill "Email" with "alice@example.com"
        And I click "Send Reset Link"
        And I open the password reset link e-mailed to "alice@example.com"
        When I fill "New Password" with "N3w!passphrase"
        And I fill "Confirm Password" with "Different!pass1"
        And I click "Reset Password"
        Then I should see "Passwords do not match"
        When I fill "New Password" with "weakpassword"
        And I fill "Confirm Password" with "weakpassword"
        And I click "Reset Password"
        Then I should see "Password must contain"

    Scenario: Asking for a reset does not reveal which addresses exist
        Given I navigate to "/auth/forgot-password"
        When I fill "Email" with "nobody@example.com"
        And I click "Send Reset Link"
        Then I should see "If an account exists with this email, a password reset link has been sent."
        And no e-mail was sent to "nobody@example.com"

    Scenario: A reset link with an unknown token is refused
        When I navigate to "/auth/reset-password?token=not-a-token"
        Then I should see "Invalid or expired reset token"
