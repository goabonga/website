Feature: VPN session management
  As an admin user with VPN permissions
  I want to view and revoke VPN sessions
  So that I can manage active VPN connections

  Background:
    Given I am a super admin

  # --- Sessions list ---

  Scenario: View VPN sessions list
    Given VPN sessions exist
    When I send a GET request to "/vpn/sessions"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View VPN sessions list unauthenticated
    Given I am not authenticated
    When I send a GET request to "/vpn/sessions"
    Then the response status code should be 302

  Scenario: View VPN sessions when service is unavailable
    Given the VPN service is unavailable
    When I send a GET request to "/vpn/sessions"
    Then the response status code should be 200
    And the response should be HTML

  # --- Revoke session ---

  Scenario: Revoke VPN session successfully
    Given revoking a VPN session succeeds
    When I send a POST request to "/vpn/sessions/ABC123DEF456/revoke"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Session+revoked"

  Scenario: Revoke VPN session failure
    Given revoking a VPN session fails
    When I send a POST request to "/vpn/sessions/ABC123DEF456/revoke"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+revoke"

  Scenario: Revoke VPN session unauthenticated
    Given I am not authenticated
    When I send a POST request to "/vpn/sessions/ABC123DEF456/revoke"
    Then the response status code should be 302
