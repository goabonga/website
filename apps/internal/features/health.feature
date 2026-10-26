Feature: Application health
  As an operator
  I want a health endpoint and a closed API surface by default
  So that the service can be monitored and does not leak its documentation

  Scenario: Health endpoint reports the service as healthy
    When I send a GET request to "/health"
    Then the response status code should be 200
    And the response should be valid JSON
    And the response JSON key "status" should equal "healthy"

  Scenario: Health endpoint is hidden from the API schema
    When I send a GET request to "/openapi.json"
    Then the response status code should be 404

  Scenario: Interactive API documentation is disabled by default
    When I send a GET request to "/docs"
    Then the response status code should be 404

  Scenario: Unknown paths return not found
    When I send a GET request to "/does-not-exist"
    Then the response status code should be 404
