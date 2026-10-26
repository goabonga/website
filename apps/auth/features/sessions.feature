Feature: Sessions and logout
    As a signed-in user
    I want my browser session to be tracked, extended while I use it and revoked when I sign out
    So that my account stays protected on shared devices

    Background:
        Given an empty user database
        And a verified user "alice@example.com" with the password "Sup3r!secret"

    Scenario: A session token is stored hashed and resolves to its user
        When a session is opened for "alice@example.com"
        Then the session token is not stored in clear
        And the session token resolves to "alice@example.com"
        And an unknown session token resolves to nobody

    Scenario: An expired session is not valid
        When a session is opened for "alice@example.com"
        And the session expired one minute ago
        Then the session token resolves to nobody

    Scenario: The CSRF token is bound to its session
        When a session is opened for "alice@example.com"
        Then the session accepts its own CSRF token
        And the session rejects the CSRF token "forged"

    Scenario: Signing out revokes the session and clears the cookies
        Given a session is opened for "alice@example.com"
        When I post to "/auth/logout/api" with the session cookie
        Then the response status is 200
        And the session token resolves to nobody
        And the response clears the session cookie

    Scenario: Signing out through the form redirects to the login page
        Given a session is opened for "alice@example.com"
        When I post to "/auth/logout" with the session cookie
        Then the response status is 303
        And the browser is redirected to a path starting with "/auth/login"
        And the session token resolves to nobody

    Scenario: Signing out without a session is refused by the API
        When I send a POST request to "/auth/logout/api"
        Then the response status is 401

    Scenario: Signing out everywhere revokes every session of the user
        Given a session is opened for "alice@example.com"
        And a second session is opened for "alice@example.com"
        When I post to "/auth/logout/all/api" with the session cookie
        Then the response status is 200
        And the user "alice@example.com" has 0 active sessions

    Scenario: A session close to its end is extended on use
        Given a session is opened for "alice@example.com"
        And the session expires in 5 minutes
        When I request "/health" with the session cookie
        Then the response sets a refreshed session cookie
        And the session lasts for about 7 days

    Scenario: A session with plenty of time left is left alone
        Given a session is opened for "alice@example.com"
        When I request "/health" with the session cookie
        Then the response does not set a session cookie

    Scenario Outline: Only verified, active users with the right password authenticate
        Given the user "alice@example.com" is <state>
        When "alice@example.com" authenticates with the password "<password>"
        Then the authentication <result>

        Examples:
            | state      | password     | result   |
            | verified   | Sup3r!secret | succeeds |
            | verified   | wrong        | fails    |
            | inactive   | Sup3r!secret | fails    |
            | unverified | Sup3r!secret | fails    |
