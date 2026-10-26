Feature: Application foundation
  As an operator
  I want the service to expose a health check and its API surface
  So that monitoring and deployment tooling can rely on it

  Scenario: Health endpoint reports the service as healthy
    When I send a GET request to "/health"
    Then the response status code should be 200
    And the response field "status" should be "healthy"
    And the response field "version" should be "0.0.0"

  Scenario: Public interactive documentation is disabled by default
    When I send a GET request to "/docs"
    Then the response status code should be 404

  Scenario: Internal API documentation is served
    When I send a GET request to "/internal/docs"
    Then the response status code should be 200

  Scenario: Cross-origin preflight requests are answered
    When a browser at origin "https://example.com" sends a preflight request to "/health"
    Then the response status code should be 200
    And the response header "access-control-allow-origin" should be present
