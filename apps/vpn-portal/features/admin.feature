Feature: Admin API
  As a VPN administrator
  I want to manage VPN sessions
  So that I can monitor and control user connections

  # --- List Sessions ---

  Scenario: List active sessions when none exist
    Given I am authenticated with "vpn:admin" scope
    And the database contains 0 active sessions
    When I send a GET request to "/api/v1/admin/sessions"
    Then the response status code should be 200
    And the response should contain "total" with integer value 0
    And the response "sessions" list should have 0 items
    And the response should contain "page" with integer value 1
    And the response should contain "per_page" with integer value 50

  Scenario: List active sessions with results
    Given I am authenticated with "vpn:admin" scope
    And the database contains 2 active sessions
    When I send a GET request to "/api/v1/admin/sessions"
    Then the response status code should be 200
    And the response should contain "total" with integer value 2
    And the response "sessions" list should have 2 items

  Scenario: List sessions with pagination
    Given I am authenticated with "vpn:admin" scope
    And the database contains 2 active sessions
    When I send a GET request to "/api/v1/admin/sessions?page=1&per_page=1"
    Then the response status code should be 200
    And the response should contain "total" with integer value 2
    And the response "sessions" list should have 1 items
    And the response should contain "page" with integer value 1
    And the response should contain "per_page" with integer value 1

  Scenario: Sessions show the assigned VPN address
    Given I am authenticated with "vpn:admin" scope
    And the database contains 1 active sessions
    When I send a GET request to "/api/v1/admin/sessions"
    Then the first session should have the assigned IP "10.8.0.2"

  Scenario: List sessions without authentication
    When I send a GET request to "/api/v1/admin/sessions"
    Then the response status code should be 401

  Scenario: List sessions with insufficient scope
    Given I am authenticated with "vpn:connect" scope
    When I send a GET request to "/api/v1/admin/sessions"
    Then the response status code should be 403

  # --- Revoke Session ---

  Scenario: Revoke an active session
    Given I am authenticated with "vpn:admin" scope
    And the certificate authority will accept revocations
    And a certificate with serial "abc123" exists
    When I send a DELETE request to "/api/v1/admin/sessions/abc123"
    Then the response status code should be 200
    And the response should contain "status" with value "revoked"
    And the response should contain "serial_number" with value "abc123"
    And the response "revoked_at" should not be null
    And the certificate "abc123" should be revoked with reason "admin_revoked"
    And the certificate authority should have revoked "abc123"

  Scenario: Revoked sessions are no longer listed
    Given I am authenticated with "vpn:admin" scope
    And the certificate authority will accept revocations
    And a certificate with serial "abc123" exists
    When I send a DELETE request to "/api/v1/admin/sessions/abc123"
    And I send a GET request to "/api/v1/admin/sessions"
    Then the response should contain "total" with integer value 0

  Scenario: Revoke a nonexistent session
    Given I am authenticated with "vpn:admin" scope
    And no certificate with serial "unknown-serial" exists
    When I send a DELETE request to "/api/v1/admin/sessions/unknown-serial"
    Then the response status code should be 404

  Scenario: Revoke a session without authentication
    When I send a DELETE request to "/api/v1/admin/sessions/abc123"
    Then the response status code should be 401

  Scenario: Revoke a session with insufficient scope
    Given I am authenticated with "vpn:connect" scope
    When I send a DELETE request to "/api/v1/admin/sessions/abc123"
    Then the response status code should be 403
