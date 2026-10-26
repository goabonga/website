Feature: Dual-stream logging
  As an operator running the service under systemd
  I want informational logs on stdout and problems on stderr
  So that each stream can be captured in its own log file

  Scenario: Informational records go to stdout
    Given logging is configured at level "DEBUG"
    When the application logs an "INFO" message "service started"
    Then stdout should contain "service started"
    And stderr should not contain "service started"

  Scenario: Warnings and errors go to stderr
    Given logging is configured at level "DEBUG"
    When the application logs an "ERROR" message "something failed"
    Then stderr should contain "something failed"
    And stdout should not contain "something failed"

  Scenario: Records below the configured level are dropped
    Given logging is configured at level "WARNING"
    When the application logs an "INFO" message "too chatty"
    Then stdout should not contain "too chatty"
    And stderr should not contain "too chatty"
