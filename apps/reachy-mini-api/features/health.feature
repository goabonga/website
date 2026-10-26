Feature: Application foundation
  As an operator
  I want a health endpoint and no public API documentation by default
  So that the service can be monitored without exposing its schema

  Scenario: Health endpoint returns healthy status
    When I send a GET request to "/health"
    Then the response status code should be 200
    And the response JSON field "status" should be "healthy"

  Scenario: Unknown endpoint returns 404
    When I send a GET request to "/does-not-exist"
    Then the response status code should be 404

  Scenario: OpenAPI documentation is disabled
    When I send a GET request to "/openapi.json"
    Then the response status code should be 404
