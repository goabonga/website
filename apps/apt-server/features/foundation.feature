Feature: Application foundation
  The service starts with its default configuration and exposes a health
  endpoint that load balancers and monitoring can probe.

  Scenario: Health check reports the service is up
    When I request "/health"
    Then the response status is 200
    And the JSON field "status" is "ok"

  Scenario: Static assets are served
    When I request "/static/favicon.ico"
    Then the response status is 200

  Scenario: Swagger UI is disabled by default
    When I request "/docs"
    Then the response status is 404

  Scenario: Unknown routes return not found
    When I request "/does-not-exist"
    Then the response status is 404

  Scenario: Default configuration is applied
    Then the service name is configured as apt-server
