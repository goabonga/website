Feature: Application foundation
  The application starts from its settings, answers a health check, applies
  a CORS policy and writes its logs to the right output streams.

  Scenario: Health check reports a healthy server
    When I request "/health"
    Then the response status is 200
    And the response JSON field "status" is "healthy"
    And the health version is the package version

  Scenario: API documentation is served by default
    When I request "/openapi.json"
    Then the response status is 200
    And the response JSON field "info.title" is "Team"

  Scenario: Cross-origin requests are allowed by default
    When a browser at the origin "https://client.example.com" requests "/health"
    Then the response status is 200
    And the response header "access-control-allow-origin" is "https://client.example.com"
    And the response header "access-control-allow-credentials" is "true"

  Scenario: Settings are read from the environment
    Given the environment variable "APP_NAME" is "Platform"
    And the environment variable "LOG_LEVEL" is "DEBUG"
    When the settings are loaded
    Then the setting "app_name" is "Platform"
    And the setting "log_level" is "DEBUG"

  Scenario: Settings have defaults for local development
    When the settings are loaded
    Then the setting "app_name" is "Team"
    And the setting "docs_enabled" is "True"
    And the setting "database_url" contains "postgresql+asyncpg"

  Scenario: Secrets are read from the systemd credentials directory first
    Given a credentials directory with "API_TOKEN" set to "from-file"
    And the environment variable "API_TOKEN" is "from-env"
    When the credential "API_TOKEN" is read
    Then the credential value is "from-file"

  Scenario: Log records are split between stdout and stderr
    Given logging is set up at level "INFO"
    When the application logs "starting" at level INFO and "failing" at level ERROR
    Then stdout contains "starting" and not "failing"
    And stderr contains "failing" and not "starting"

  Scenario: Log lines carry the request context
    Given logging is set up at level "INFO"
    And the request context is user "user-1" and client "client-1"
    When the application logs "hello" at level INFO and "oops" at level ERROR
    Then stdout contains "user=user-1"
    And stdout contains "client=client-1"
