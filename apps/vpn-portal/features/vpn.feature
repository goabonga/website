Feature: VPN client API
  As a VPN user
  I want to obtain and release a short-lived VPN certificate
  So that I can securely access internal resources

  Scenario: Connect to VPN successfully
    Given I am authenticated with "vpn:connect" scope
    And the certificate authority will sign certificates
    When I send a POST request to "/api/v1/vpn/connect"
    Then the response status code should be 200
    And the response body should include "certificate"
    And the response body should include "private_key"
    And the response body should include "ca_certificate"
    And the response body should include "ovpn_config"
    And the response body should include "expires_at"
    And the response body should include "vpn_server"
    And the response body should include "vpn_port"
    And the response should contain "assigned_routes" as a list
    And one certificate should be recorded

  Scenario: Connect to VPN with device name and custom TTL
    Given I am authenticated with "vpn:connect" scope
    And the certificate authority will sign certificates
    When I send a POST request to "/api/v1/vpn/connect" with body:
      """
      {"device_name": "laptop", "certificate_ttl": 600}
      """
    Then the response status code should be 200
    And the recorded certificate should have the device name "laptop"
    And the certificate authority should have been asked for 10 minutes

  Scenario: Routes follow the scopes of the user
    Given I am authenticated with the scopes "vpn:connect vpn:internal"
    And the certificate authority will sign certificates
    When I send a POST request to "/api/v1/vpn/connect"
    Then the response status code should be 200
    And the assigned routes should be "10.0.0.0/8,10.8.0.0/24"

  Scenario: Connect to VPN fails when the certificate authority fails
    Given I am authenticated with "vpn:connect" scope
    And the certificate authority will fail
    When I send a POST request to "/api/v1/vpn/connect"
    Then the response status code should be 500
    And the response body should include "detail"
    And no certificate should be recorded

  Scenario: Connect to VPN without authentication
    When I send a POST request to "/api/v1/vpn/connect"
    Then the response status code should be 401

  Scenario: Connect to VPN with insufficient scope
    Given I am authenticated with "openid" scope
    When I send a POST request to "/api/v1/vpn/connect"
    Then the response status code should be 403

  Scenario: Disconnect from VPN when connected
    Given I am authenticated with "vpn:connect" scope
    And the certificate authority will accept revocations
    And the user has an active certificate
    When I send a POST request to "/api/v1/vpn/disconnect"
    Then the response status code should be 200
    And the response should contain "status" with value "disconnected"
    And the response "revoked_at" should not be null
    And the certificate authority should have revoked the certificate

  Scenario: Disconnect from VPN when not connected
    Given I am authenticated with "vpn:connect" scope
    And the user has no active certificate
    When I send a POST request to "/api/v1/vpn/disconnect"
    Then the response status code should be 200
    And the response should contain "status" with value "not_connected"
    And the response "revoked_at" should be null

  Scenario: Revocation survives a certificate authority outage
    Given I am authenticated with "vpn:connect" scope
    And the certificate authority will fail
    And the user has an active certificate
    When I send a POST request to "/api/v1/vpn/disconnect"
    Then the response status code should be 200
    And the response should contain "status" with value "disconnected"

  Scenario: Disconnect from VPN without authentication
    When I send a POST request to "/api/v1/vpn/disconnect"
    Then the response status code should be 401

  Scenario: Check VPN status when connected
    Given I am authenticated with "vpn:connect" scope
    And the user has an active certificate
    When I send a GET request to "/api/v1/vpn/status"
    Then the response status code should be 200
    And the response should contain "connected" with value "true"
    And the response "certificate_serial" should not be null
    And the response "common_name" should not be null
    And the response "expires_at" should not be null
    And the response should contain "assigned_routes" as a list

  Scenario: Check VPN status when not connected
    Given I am authenticated with "vpn:connect" scope
    And the user has no active certificate
    When I send a GET request to "/api/v1/vpn/status"
    Then the response status code should be 200
    And the response should contain "connected" with value "false"
    And the response "certificate_serial" should be null
    And the response "common_name" should be null
    And the response "expires_at" should be null

  Scenario: Check VPN status without authentication
    When I send a GET request to "/api/v1/vpn/status"
    Then the response status code should be 401
