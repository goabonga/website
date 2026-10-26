Feature: Application foundation
  The service starts, answers health checks and hides its interactive
  documentation unless it is explicitly enabled.

  Scenario: Health check reports a healthy service
    When I send a GET to "/health"
    Then the response status should be 200
    And the response JSON "status" should be "healthy"

  Scenario: Health check does not leak any other field
    When I send a GET to "/health"
    Then the response status should be 200
    And the response JSON should contain "status"
    And the response should not contain "version"

  Scenario: Interactive documentation is disabled by default
    When I send a GET to "/docs"
    Then the response status should be 404

  Scenario: OpenAPI schema is disabled by default
    When I send a GET to "/openapi.json"
    Then the response status should be 404

  Scenario: Unknown routes return 404
    When I send a GET to "/does-not-exist"
    Then the response status should be 404

  Scenario: CORS preflight is answered for the configured origin
    When I send a CORS preflight to "/health" from "https://frontend.example"
    Then the response status should be 200
    And the response header "access-control-allow-origin" should be "https://frontend.example"
