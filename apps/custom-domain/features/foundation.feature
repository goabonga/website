Feature: Application foundation
  The service exposes a health check and a root endpoint, and keeps its
  interactive documentation disabled unless it is explicitly enabled.

  Scenario: Health check reports the service as healthy
    When I send a GET request to "/health"
    Then the response status is 200
    And the JSON field "status" equals "healthy"

  Scenario: Root endpoint describes the service
    When I send a GET request to "/"
    Then the response status is 200
    And the JSON field "service" equals "custom-domain"
    And the JSON field "version" is a semantic version
    And the JSON field "docs" is null

  Scenario: Interactive documentation is disabled by default
    When I send a GET request to "/docs"
    Then the response status is 404
