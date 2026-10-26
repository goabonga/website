Feature: Anonymous sessions
  As a visitor without an account
  I want a cookie-backed session
  So that my conversation is kept between requests

  Background:
    Given an API exposing the chat context at "/context"

  Scenario: A first visit creates a session
    Given session creation is allowed
    When I send a GET request to "/context"
    Then the response status code should be 200
    And the response JSON should contain "is_authenticated" with value "False"
    And the response JSON should contain "session_created" with value "True"
    And the response JSON "session_id" should not be null
    And a session creation should have been recorded

  Scenario: A known session cookie is reused
    Given the session "abcdef12-3456-7890-abcd-ef1234567890" exists
    When I request "/context" with the session cookie "abcdef12-3456-7890-abcd-ef1234567890"
    Then the response JSON should contain "session_id" with value "abcdef12-3456-7890-abcd-ef1234567890"
    And the response JSON should contain "session_created" with value "False"
    And no session creation should have been recorded

  Scenario: An unknown session id is registered
    Given session creation is allowed
    When I request "/context" with the session cookie "11111111-2222-3333-4444-555555555555"
    Then the response JSON should contain "session_id" with value "11111111-2222-3333-4444-555555555555"
    And the response JSON should contain "session_created" with value "True"

  Scenario: A malformed cookie is ignored
    Given session creation is allowed
    When I request "/context" with the session cookie "not-a-uuid"
    Then the response JSON should contain "session_created" with value "True"
    And the response JSON "session_id" should not be null

  Scenario: Session creation is rate limited
    Given session creation is refused
    When I send a GET request to "/context"
    Then the response status code should be 429
    And the response header "Retry-After" should be "86400"

  Scenario: An authenticated user takes priority over the cookie
    Given I am the authenticated user "12345678-1234-5678-1234-567812345678"
    When I request "/context" with the session cookie "abcdef12-3456-7890-abcd-ef1234567890"
    Then the response JSON should contain "is_authenticated" with value "True"
    And the response JSON should contain "anonymous_session_id" with value "abcdef12-3456-7890-abcd-ef1234567890"
    And the response JSON "session_id" should be null
