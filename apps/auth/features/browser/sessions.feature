@browser
Feature: Sessions and logout in a browser
    As a signed-in user
    I want my session cookie to behave like a session cookie in a real browser
    So that it is protected from scripts, extended while I use the service and removed when I sign out

    Background:
        Given an empty user database
        And a verified user "alice@example.com" with the password "Sup3r!secret"
        And a session is opened for "alice@example.com"
        And the browser holds the cookie of the session

    Scenario: The session cookie is hidden from the scripts of the page
        When I navigate to "/health"
        Then the scripts of the page cannot read the session cookie

    Scenario: A session close to its end is extended while the user browses
        Given the session expires in 10 minutes
        When I navigate to "/health"
        Then the session cookie expires in about 7 days
        And the session cookie of the browser is HttpOnly, Secure and SameSite Lax
        And the user "alice@example.com" has 1 active sessions

    Scenario: A session far from its end is left alone
        When I navigate to "/health"
        Then the session cookie expires in about 7 days

    Scenario: Signing out through the API removes the cookie from the browser
        Given I navigate to "/health"
        When the page posts to "/auth/logout/api" without leaving the page
        Then the page request was answered with status 200
        And the browser no longer holds the session cookie
        And the session token resolves to nobody

    Scenario: Signing out through a form removes the cookie and returns to the login page
        Given I navigate to "/health"
        When the page submits a form posting to "/auth/logout"
        Then the URL should contain "/auth/login"
        And the browser no longer holds the session cookie
        And the session token resolves to nobody

    Scenario: Signing out everywhere revokes every session of the user
        Given a second session is opened for "alice@example.com"
        And I navigate to "/health"
        When the page posts to "/auth/logout/all/api" without leaving the page
        Then the page request was answered with status 200
        And the user "alice@example.com" has 0 active sessions
        And the browser no longer holds the session cookie

    Scenario: A request without a session cannot sign out
        Given the browser holds no cookie
        And I navigate to "/health"
        When the page posts to "/auth/logout/api" without leaving the page
        Then the page request was answered with status 401
