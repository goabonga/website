Feature: Health check
  As a monitoring system
  I want to check the service health
  So that I can detect outages

  Scenario: Health endpoint returns healthy status
    When I send a GET request to "/health"
    Then the response status code should be 200
    And the response should be valid JSON
    And the response JSON key "status" should equal "healthy"

  Scenario: Unknown endpoint returns 404
    When I send a GET request to "/unknown"
    Then the response status code should be 404

  Scenario: OpenAPI documentation is disabled
    When I send a GET request to "/docs"
    Then the response status code should be 404
