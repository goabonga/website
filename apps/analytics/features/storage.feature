Feature: Session and event storage
  As the analytics service
  I want to persist visitor sessions and their events
  So that traffic can be analysed later

  Scenario: A stored session can be read back
    Given a stored session "sess-1"
    Then the database should contain 1 session
    And the stored session "sess-1" should have first and last seen timestamps

  Scenario: Session identifiers are unique
    Given a stored session "sess-1"
    When I try to store another session "sess-1"
    Then the database should reject the duplicate session

  Scenario: Events belong to a session
    Given a stored session "sess-1"
    And the session "sess-1" has an event "page_view"
    And the session "sess-1" has an event "click"
    Then the session "sess-1" should have 2 events
    And the database should contain 2 events

  Scenario: Event data is stored as JSON
    Given a stored session "sess-1"
    And the session "sess-1" has an event "click" with data {"button": "signup", "position": 3}
    Then the first event of session "sess-1" should have data key "button" equal to "signup"

  Scenario: Deleting a session deletes its events
    Given a stored session "sess-1"
    And the session "sess-1" has an event "page_view"
    When I delete the session "sess-1"
    Then the database should contain 0 sessions
    And the database should contain 0 events

  Scenario Outline: Database URLs use the asyncpg driver
    Then the database URL "<url>" should become "<async_url>"

    Examples:
      | url                              | async_url                                |
      | postgres://u:p@host:5432/db      | postgresql+asyncpg://u:p@host:5432/db    |
      | postgresql://u:p@host:5432/db    | postgresql+asyncpg://u:p@host:5432/db    |
      | postgresql+asyncpg://u@host/db   | postgresql+asyncpg://u@host/db           |
