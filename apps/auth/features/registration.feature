Feature: Registration and email verification
    As a visitor
    I want to create an account and prove that I own my e-mail address
    So that I can sign in to the service

    Background:
        Given an empty user database
        And outgoing e-mails are captured

    Scenario: A visitor registers through the JSON API
        When I register "alice@example.com" with the password "Sup3r!secret" through the API
        Then the response status is 200
        And the response JSON field "email" is "alice@example.com"
        And the account "alice@example.com" exists and is not verified yet
        And the stored password of "alice@example.com" is an Argon2id hash
        And the profile of "alice@example.com" has the nickname "ally"
        And a verification e-mail with a 6 digit code was sent to "alice@example.com"

    Scenario Outline: Weak passwords are refused
        When I register "bob@example.com" with the password "<password>" through the API
        Then the response status is 422
        And no account exists for "bob@example.com"

        Examples:
            | password     |
            | Sh0rt!       |
            | nouppercase1! |
            | NOLOWERCASE1! |
            | NoDigits!!    |
            | NoSpecial123  |

    Scenario: An address can only be registered once
        Given the address "alice@example.com" is registered
        When I register "Alice@Example.com" with the password "Sup3r!secret" through the API
        Then the response status is 400
        And the response JSON field "detail" is "Email already registered"

    Scenario: The code received by e-mail verifies the address
        Given the address "alice@example.com" is registered
        When I verify "alice@example.com" with the code received by e-mail
        Then the response status is 200
        And the response JSON field "message" is "Email verified successfully"
        And the account "alice@example.com" exists and is verified

    Scenario: A wrong code does not verify the address
        Given the address "alice@example.com" is registered
        When I verify "alice@example.com" with the code "000000"
        Then the response status is 400
        And the account "alice@example.com" exists and is not verified yet

    Scenario: A code can only be used once
        Given the address "alice@example.com" is registered
        And I verify "alice@example.com" with the code received by e-mail
        When I verify "alice@example.com" with the code received by e-mail
        Then the response status is 400

    Scenario: A new code can be requested without revealing which addresses exist
        Given the address "alice@example.com" is registered
        When I ask for a new verification code for "alice@example.com"
        Then the response status is 200
        And 2 e-mails were sent to "alice@example.com"
        When I ask for a new verification code for "nobody@example.com"
        Then the response status is 200
        And no e-mail was sent to "nobody@example.com"

    Scenario: The registration form is served and submitted
        When I send a GET request to "/auth/register"
        Then the response status is 200
        And the response body contains "password_confirm"
        When I submit the registration form for "carol@example.com"
        Then the response status is 303
        And the browser is redirected to a path starting with "/auth/verify-email"
        And the account "carol@example.com" exists and is not verified yet

    Scenario: The registration form checks the password confirmation
        When I submit the registration form for "dave@example.com" with a different confirmation
        Then the response status is 400
        And no account exists for "dave@example.com"

    Scenario: Verification e-mails are rendered from the branded templates
        Given the address "alice@example.com" is registered
        Then the verification e-mail to "alice@example.com" is an HTML document
        And the verification e-mail to "alice@example.com" has a plain text alternative

    Scenario: Avatars must be small images
        When an avatar of type "image/png" and 1 KB is uploaded
        Then the avatar is stored under "avatars/"
        When an avatar of type "text/plain" and 1 KB is uploaded
        Then the upload is refused with "Invalid file type"
        When an avatar of type "image/png" and 6 MB is uploaded
        Then the upload is refused with "File too large"
