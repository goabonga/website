Feature: Internal API
  As the OpenVPN server
  I want to validate certificates and track connections
  So that I can enforce access control and audit VPN usage

  # --- Validate Certificate ---

  Scenario: Validate a valid certificate
    Given I am authenticated with "vpn:server" scope
    And a certificate with common name "vpn-user-123-1700000000" is valid
    When I send a POST request to "/api/v1/internal/validate" with body:
      """
      {"common_name": "vpn-user-123-1700000000", "client_ip": "203.0.113.1"}
      """
    Then the response status code should be 200
    And the response should contain "valid" with value "true"
    And the response "reason" should be null
    And the response should contain "routes" as a list
    And the response "routes" list should have 2 items

  Scenario: Validate an unknown certificate
    Given I am authenticated with "vpn:server" scope
    And no certificate with common name "vpn-unknown" exists
    When I send a POST request to "/api/v1/internal/validate" with body:
      """
      {"common_name": "vpn-unknown", "client_ip": "203.0.113.1"}
      """
    Then the response status code should be 200
    And the response should contain "valid" with value "false"
    And the response should contain "reason" with value "Certificate not found"

  Scenario: Validate a revoked certificate
    Given I am authenticated with "vpn:server" scope
    And a certificate with common name "vpn-revoked" is revoked
    When I send a POST request to "/api/v1/internal/validate" with body:
      """
      {"common_name": "vpn-revoked", "client_ip": "203.0.113.1"}
      """
    Then the response status code should be 200
    And the response should contain "valid" with value "false"
    And the response should contain "reason" with value "Certificate revoked"

  Scenario: Validate an expired certificate
    Given I am authenticated with "vpn:server" scope
    And a certificate with common name "vpn-expired" is expired
    When I send a POST request to "/api/v1/internal/validate" with body:
      """
      {"common_name": "vpn-expired", "client_ip": "203.0.113.1"}
      """
    Then the response status code should be 200
    And the response should contain "valid" with value "false"
    And the response should contain "reason" with value "Certificate expired"

  Scenario: Validate without authentication
    When I send a POST request to "/api/v1/internal/validate" with body:
      """
      {"common_name": "vpn-user-123", "client_ip": "203.0.113.1"}
      """
    Then the response status code should be 401

  Scenario: Validate with insufficient scope
    Given I am authenticated with "vpn:connect" scope
    When I send a POST request to "/api/v1/internal/validate" with body:
      """
      {"common_name": "vpn-user-123", "client_ip": "203.0.113.1"}
      """
    Then the response status code should be 403

  # --- Record Connection ---

  Scenario: Record a client connection
    Given I am authenticated with "vpn:server" scope
    And a certificate with common name "vpn-user-456" exists in the database
    When I send a POST request to "/api/v1/internal/connect" with body:
      """
      {"common_name": "vpn-user-456", "client_ip": "203.0.113.10", "assigned_ip": "10.8.0.5"}
      """
    Then the response status code should be 200
    And the response should contain "status" with value "connected"
    And an active connection should be recorded for "vpn-user-456" from "10.8.0.5"

  Scenario: Record connection for unknown certificate
    Given I am authenticated with "vpn:server" scope
    And no certificate with common name "vpn-unknown" exists
    When I send a POST request to "/api/v1/internal/connect" with body:
      """
      {"common_name": "vpn-unknown", "client_ip": "203.0.113.10", "assigned_ip": "10.8.0.5"}
      """
    Then the response status code should be 200
    And the response should contain "status" with value "certificate_not_found"
    And no connection should be recorded

  Scenario: Wildcard scope is accepted for the internal API
    Given I am authenticated with "vpn:*" scope
    And a certificate with common name "vpn-user-456" exists in the database
    When I send a POST request to "/api/v1/internal/connect" with body:
      """
      {"common_name": "vpn-user-456", "client_ip": "203.0.113.10", "assigned_ip": "10.8.0.5"}
      """
    Then the response status code should be 200

  Scenario: Record connection without authentication
    When I send a POST request to "/api/v1/internal/connect" with body:
      """
      {"common_name": "vpn-user-456", "client_ip": "203.0.113.10", "assigned_ip": "10.8.0.5"}
      """
    Then the response status code should be 401

  # --- Record Disconnection ---

  Scenario: Record a client disconnection
    Given I am authenticated with "vpn:server" scope
    And a connection for common name "vpn-user-789" is active
    When I send a POST request to "/api/v1/internal/disconnect" with body:
      """
      {"common_name": "vpn-user-789", "bytes_received": 1048576, "bytes_sent": 524288}
      """
    Then the response status code should be 200
    And the response should contain "status" with value "disconnected"
    And the connection of "vpn-user-789" should be closed with 1048576 bytes received and 524288 bytes sent

  Scenario: Record disconnection with no active connection
    Given I am authenticated with "vpn:server" scope
    And no active connection for common name "vpn-no-conn" exists
    When I send a POST request to "/api/v1/internal/disconnect" with body:
      """
      {"common_name": "vpn-no-conn", "bytes_received": 0, "bytes_sent": 0}
      """
    Then the response status code should be 200
    And the response should contain "status" with value "connection_not_found"

  Scenario: Record disconnection without authentication
    When I send a POST request to "/api/v1/internal/disconnect" with body:
      """
      {"common_name": "vpn-user-789", "bytes_received": 0, "bytes_sent": 0}
      """
    Then the response status code should be 401
