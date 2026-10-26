Feature: Server and services status
  As a system administrator
  I want to monitor the server and the services status
  So that I can detect issues early

  Scenario: Status requires authentication
    When I send a GET request to "/api/status/server"
    Then the response status code should be 401

  Scenario: Status requires the status scope
    Given I am authenticated with scope "reachy:reports:read"
    When I request "GET /api/status/server"
    Then the response status code should be 403

  Scenario: Get the server status
    Given I am authenticated with scope "reachy:status:read"
    When I request "GET /api/status/server"
    Then the response status code should be 200
    And the response should contain "timestamp"
    And the response should contain "hostname"
    And the response should contain "platform"
    And the response should contain "python_version"
    And the response JSON field "status" should be "online"

  Scenario: Get the services status
    Given I am authenticated with scope "reachy:status:read"
    When I request "GET /api/status/services"
    Then the response status code should be 200
    And the response field "services" should be a list
    And the response field "services" should have 3 items
    And each item in "services" should contain "name"
    And each item in "services" should contain "status"
    And each item in "services" should contain "port"
