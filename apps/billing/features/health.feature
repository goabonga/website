Feature: Health Check
  The health endpoint returns the service status.

  Scenario: Health check returns healthy
    Given I am not authenticated
    When I send a GET to "/health"
    Then the response status should be 200
    And the response JSON "status" should be "healthy"
    And the response JSON should contain "version"

  Scenario: Interactive API documentation is disabled by default
    Given I am not authenticated
    When I send a GET to "/docs"
    Then the response status should be 404
