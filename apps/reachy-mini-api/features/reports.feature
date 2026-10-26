Feature: Reports and notifications
  As the Reachy Mini robot
  I want to fetch daily reports, quick updates and notifications
  So that I can announce them to the user

  Scenario: Reports require authentication
    When I send a GET request to "/api/reports/daily"
    Then the response status code should be 401

  Scenario: Reports require the reports scope
    Given I am authenticated with scope "reachy:notifications:read"
    When I request "GET /api/reports/daily"
    Then the response status code should be 403

  Scenario: Get the daily report
    Given I am authenticated with scope "reachy:reports:read"
    When I request "GET /api/reports/daily"
    Then the response status code should be 200
    And the response should contain "date"
    And the response should contain "summary"
    And the response should contain "weather"
    And the response field "tasks_completed" should be 5
    And the response field "tasks_pending" should be 3
    And the response field "notifications" should have 2 items
    And the response field "calendar_events" should be a list

  Scenario: Get a quick update
    Given I am authenticated with scope "reachy:reports:read"
    When I request "GET /api/reports/quick"
    Then the response status code should be 200
    And the response JSON field "priority" should be "normal"
    And the response JSON field "category" should be "status"

  Scenario: Get the notifications
    Given I am authenticated with scope "reachy:notifications:read"
    When I request "GET /api/reports/notifications"
    Then the response status code should be 200
    And the response field "count" should be 2
    And each item in "notifications" should contain "id"
    And each item in "notifications" should contain "message"
    And each item in "notifications" should contain "read"

  Scenario: Notifications require their own scope
    Given I am authenticated with scope "reachy:reports:read"
    When I request "GET /api/reports/notifications"
    Then the response status code should be 403
