@browser
Feature: VPN session management in a browser
  As an operator with the VPN permission
  I want to list the VPN sessions and revoke one
  So that I can control the active VPN connections

  # --- Access and sidebar ---

  Scenario: The sessions are listed for a user holding the VPN scope
    Given VPN sessions exist
    And I sign in with the scopes "vpn:admin"
    When I navigate to "/vpn/sessions"
    Then the page title should be "VPN Sessions - Internal Admin"
    And I should see "Active Sessions (1)"
    And I should see "testuser"
    And I should see "ABC123DEF456"
    And I should see "10.8.0.0/24"
    And the sidebar menu should highlight only "VPN"
    And the browser should report no errors

  Scenario: Only the holders of the VPN scope see the VPN link
    Given the analytics overview returns data
    And I sign in with the scopes "analytics:*"
    When I navigate to "/analytics"
    Then the sidebar menu should not have a link "VPN"

  Scenario: The VPN link is shown on the other pages to the holders of the VPN scope
    Given the analytics overview returns data
    And I sign in with the scopes "analytics:* vpn:admin"
    When I navigate to "/analytics"
    Then the sidebar menu should have a link "VPN" to "/vpn/sessions"
    When I follow the sidebar link "VPN"
    Then the URL should be "/vpn/sessions"

  Scenario: A user without the VPN scope gets the access denied page
    Given VPN sessions exist
    And I sign in with the scopes "analytics:*"
    When I navigate to "/vpn/sessions"
    Then the page title should contain "Access Denied"
    And I should see "vpn:admin"
    And I should not see "testuser"

  Scenario: An anonymous visitor is sent to the provider and comes back to the sessions
    Given VPN sessions exist
    And a user holding the scopes "vpn:admin" exists at the provider
    When I navigate to "/vpn/sessions"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/vpn/sessions"
    And I should see "testuser"

  Scenario: The list tells when the VPN service is unavailable
    Given the VPN service is unavailable
    And I sign in with the scopes "vpn:admin"
    When I navigate to "/vpn/sessions"
    Then I should see "Failed to fetch VPN sessions"
    And the sidebar menu should highlight only "VPN"

  # --- Revoking a session ---

  Scenario: Revoking a session asks to confirm and reports the success
    Given VPN sessions exist
    And revoking a VPN session succeeds
    And I sign in with the scopes "vpn:admin"
    When I navigate to "/vpn/sessions"
    And I click "Revoke"
    Then I should see "Revoke session for testuser?"
    When I click "Confirm"
    Then the URL should contain "/vpn/sessions?success="
    And I should see "Session revoked successfully"

  Scenario: Cancelling the confirmation revokes nothing
    Given VPN sessions exist
    And I sign in with the scopes "vpn:admin"
    When I navigate to "/vpn/sessions"
    And I click "Revoke"
    And I click "Cancel"
    Then "Revoke session for testuser?" should be hidden
    And the URL should be "/vpn/sessions"

  Scenario: A session that cannot be revoked is reported
    Given VPN sessions exist
    And revoking a VPN session fails
    And I sign in with the scopes "vpn:admin"
    When I navigate to "/vpn/sessions"
    And I click "Revoke"
    And I click "Confirm"
    Then I should see "Failed to revoke session"

  Scenario: A session of a user with an apostrophe in the name can be revoked
    Given a VPN session of the user "o'brien" with the certificate "AB'CD" exists
    And revoking a VPN session succeeds
    And I sign in with the scopes "vpn:admin"
    When I navigate to "/vpn/sessions"
    And I click "Revoke"
    Then I should see "Revoke session for o'brien?"
    When I click "Confirm"
    Then I should see "Session revoked successfully"
    And the browser should report no errors
