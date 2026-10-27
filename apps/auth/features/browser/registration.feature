@browser
Feature: Registration and email verification in a browser
    As a visitor
    I want to create an account from the registration page and confirm my address
    So that I can sign in to the service

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And the application is served at its public address

    Scenario: The registration page offers the form and a link to sign in
        When I navigate to "/auth/register"
        Then the page title should be "Register - Auth"
        And I should see "Create Account"
        And "Nickname" should be visible
        And "Confirm Password" should be visible
        And the page should link "Sign in" to "/auth/login"
        And the browser should report no errors

    Scenario: The password requirements react while the visitor types
        Given I navigate to "/auth/register"
        When I fill "Password" with "weak"
        Then the password requirement "At least 8 characters" is unmet
        And the password requirement "At least one uppercase letter" is unmet
        When I fill "Password" with "Sup3r!secret"
        Then the password requirement "At least 8 characters" is met
        And the password requirement "At least one uppercase letter" is met
        And the password requirement "At least one digit" is met
        And the password requirement "At least one special character" is met

    Scenario: A visitor registers and confirms the address with the e-mailed code
        Given I navigate to "/auth/register"
        When I fill the registration form for "carol@example.com" with the password "Sup3r!secret"
        And I click "Register"
        Then the URL should contain "/auth/verify-email"
        And the field "Email" should have the value "carol@example.com"
        And I should see "Verify Your Email"
        And the address "carol@example.com" is unverified in the database
        When I enter the e-mailed code of "carol@example.com"
        And I click "Verify Email"
        Then the URL should contain "/auth/login?verified=1"
        And the address "carol@example.com" is verified in the database

    Scenario: The link of the verification e-mail leads to the verification page
        Given I navigate to "/auth/register"
        And I fill the registration form for "carol@example.com" with the password "Sup3r!secret"
        And I click "Register"
        When I open the verification link e-mailed to "carol@example.com"
        Then the URL should contain "/auth/verify-email?email=carol@example.com"
        And the field "Email" should have the value "carol@example.com"
        When I enter the e-mailed code of "carol@example.com"
        And I click "Verify Email"
        Then the address "carol@example.com" is verified in the database

    Scenario: A wrong code is refused and a new one can be requested
        Given I navigate to "/auth/register"
        And I fill the registration form for "carol@example.com" with the password "Sup3r!secret"
        And I click "Register"
        When I fill "Verification Code" with "000000"
        And I click "Verify Email"
        Then I should see "Invalid or expired verification code"
        And the address "carol@example.com" is unverified in the database
        When I click "Resend verification code"
        Then 2 e-mails were sent to "carol@example.com"
        When I enter the e-mailed code of "carol@example.com"
        And I click "Verify Email"
        Then the address "carol@example.com" is verified in the database

    Scenario: An address that is already registered is refused
        Given the address "alice@example.com" is registered
        And I navigate to "/auth/register"
        When I fill the registration form for "alice@example.com" with the password "Sup3r!secret"
        And I click "Register"
        Then I should see "Email already registered"
        And the URL should contain "/auth/register"
        And the field "Email" should have the value "alice@example.com"

    Scenario: The browser stops a weak password or a wrong confirmation before sending it
        Given the browser records the dialogs of the page
        And I navigate to "/auth/register"
        When I fill the registration form for "dave@example.com" with the password "weakpass1"
        And I click "Register"
        Then the page showed a dialog saying "Password does not meet all requirements."
        And the URL should contain "/auth/register"
        And no account exists for "dave@example.com"
        When I fill "Password" with "Sup3r!secret"
        And I fill "Confirm Password" with "Other!secret1"
        And I click "Register"
        Then the page showed a dialog saying "Passwords do not match."
        And no account exists for "dave@example.com"

    Scenario: A visitor registers with a profile picture
        Given I navigate to "/auth/register"
        When I fill the registration form for "erin@example.com" with the password "Sup3r!secret"
        And I choose the avatar file "erin.png"
        And I click "Register"
        Then the URL should contain "/auth/verify-email"
        And the profile picture of "erin@example.com" is stored under the uploads
