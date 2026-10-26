Feature: Dual-stream logging
  Informational records go to standard output and warnings or errors go to
  standard error, so that systemd can store them in separate files.

  Scenario: Informational and warning records use different streams
    Given logging is configured at level "INFO"
    When an info record "all-good" and a warning record "careful" are logged
    Then standard output contains "all-good"
    And standard output does not contain "careful"
    And standard error contains "careful"
    And standard error does not contain "all-good"

  Scenario: Records below the configured level are dropped
    Given logging is configured at level "WARNING"
    When an info record "all-good" and a warning record "careful" are logged
    Then standard output does not contain "all-good"
    And standard error contains "careful"

  Scenario: Request context is part of every log line
    Given logging is configured at level "INFO"
    And the request context has user "alice" and client "web"
    When an info record "hello" and a warning record "careful" are logged
    Then standard output contains "user=alice | client=web"

  Scenario: A health check leaves a log record
    Given logging is configured at level "INFO"
    When I request "/health"
    Then the response status is 200
    And standard output contains "Health check requested"
