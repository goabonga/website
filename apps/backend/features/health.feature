Feature: Health Check Endpoint
  As a monitoring system or load balancer
  I want to check the health status of the API
  So that I can determine if the service is operational

  Scenario: Health check returns healthy status
    When I send a GET request to "/health"
    Then the response status code should be 200
    And the response JSON should contain "status" with value "healthy"

  Scenario: Health check response has correct structure
    When I send a GET request to "/health"
    Then the response status code should be 200
    And the response JSON should have exactly the keys "status"
