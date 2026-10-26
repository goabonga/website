Feature: Application foundation
  As an operator
  I want the portal to start with sane defaults and report its health
  So that I can monitor it and configure it from the environment

  Scenario: Application reports healthy status
    When I send a GET request to "/health"
    Then the response status code should be 200
    And the response should contain "status" with value "healthy"

  Scenario: API documentation is served
    When I send a GET request to "/openapi.json"
    Then the response status code should be 200
    And the response should contain "info" with title "VPN Portal"

  Scenario: Default settings
    Given no portal setting is defined in the environment
    When the settings are loaded
    Then the application name should be "VPN Portal"
    And the log level should be "INFO"

  Scenario: Settings overridden by the environment
    Given the environment variable "LOG_LEVEL" is "DEBUG"
    And the environment variable "APP_NAME" is "Portal"
    When the settings are loaded
    Then the application name should be "Portal"
    And the log level should be "DEBUG"

  Scenario: Logging is split between stdout and stderr
    Given logging is configured on a clean root logger
    When an INFO record and an ERROR record are emitted
    Then the INFO record should be written to stdout only
    And the ERROR record should be written to stderr only
