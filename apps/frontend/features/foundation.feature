Feature: Application foundation
  The frontend server exposes a health endpoint, hides its API documentation
  unless asked to show it, and applies a configurable CORS policy.

  Scenario: Health check reports a healthy server
    When I request "/health"
    Then the response status is 200
    And the response JSON field "status" is "healthy"

  Scenario: API documentation is disabled by default
    When I request "/docs"
    Then the response status is 404

  Scenario: API documentation can be enabled
    Given the setting "docs_enabled" is "true"
    When I request "/docs"
    Then the response status is 200

  Scenario: Cross-origin requests are allowed by default
    When I send "/health" with header "Origin" set to "https://example.org"
    Then the response status is 200
    And the response header "access-control-allow-origin" is present

  Scenario: Cross-origin requests can be restricted to listed origins
    Given the setting "cors_origins" is the list "https://a.test"
    When I send "/health" with header "Origin" set to "https://a.test"
    Then the response header "access-control-allow-origin" is "https://a.test"
    When I send "/health" with header "Origin" set to "https://b.test"
    Then the response header "access-control-allow-origin" is absent
