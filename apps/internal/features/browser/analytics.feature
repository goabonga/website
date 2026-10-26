@browser
Feature: Analytics dashboards in a browser
  As an operator with analytics permissions
  I want to browse the analytics dashboards, the campaigns and the IP addresses
  So that I can monitor website traffic

  Background:
    Given the analytics overview returns data
    And the campaigns list returns data
    And a campaign exists with id "11111111-1111-1111-1111-111111111111"
    And the IP stats returns data
    And IP detail exists for "192.168.1.1"

  # --- Signing in and the sidebar ---

  Scenario: An anonymous visitor is sent to the provider and lands on the page asked for
    Given a user holding the scopes "analytics:*" exists at the provider
    When I navigate to "/analytics"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/analytics"
    And I should see "Analytics Dashboard"
    And the page title should be "Analytics Dashboard - Internal Admin"
    And the browser should report no errors

  Scenario: The query of the page asked for survives the login
    Given a user holding the scopes "analytics:*" exists at the provider
    When I navigate to "/analytics/ips?days=7&limit=50"
    And I sign in at the provider
    Then the URL should be "/analytics/ips?days=7&limit=50"

  Scenario: The sidebar highlights the analytics section on every page of the feature
    Given I sign in with the scopes "analytics:*"
    When I navigate to "/analytics"
    Then the sidebar menu should highlight only "Analytics"
    And the sidebar menu should show the signed in user
    When I navigate to "/analytics/campaigns"
    Then the sidebar menu should highlight only "Analytics"
    When I navigate to "/analytics/campaigns/11111111-1111-1111-1111-111111111111"
    Then the sidebar menu should highlight only "Analytics"
    When I navigate to "/analytics/ips"
    Then the sidebar menu should highlight only "Analytics"
    When I navigate to "/analytics/ips/192.168.1.1"
    Then the sidebar menu should highlight only "Analytics"

  Scenario: The sidebar links lead to the sections
    Given I sign in with the scopes "analytics:*"
    When I navigate to "/analytics"
    Then the sidebar menu should have a link "Analytics" to "/analytics"
    When I follow the sidebar link "Analytics"
    Then the URL should be "/analytics"

  Scenario: Signing out from the sidebar ends the session
    Given I sign in with the scopes "analytics:*"
    And the provider ends every session
    When I navigate to "/analytics"
    And I sign out from the sidebar
    Then the cookie "access_token" should not be set
    And I should be asked to sign in at the provider

  # --- Dashboard ---

  Scenario: The dashboard shows the statistics of the period
    Given I sign in with the scopes "analytics:*"
    When I navigate to "/analytics"
    Then I should see "TOTAL SESSIONS"
    And I should see "UNIQUE VISITORS"
    And I should see "192.168.1.1"

  Scenario: Changing the period reloads the dashboard
    Given I sign in with the scopes "analytics:*"
    When I navigate to "/analytics"
    And I select "Last 7 days" from "css=#days"
    Then the URL should be "/analytics?days=7"

  Scenario: The dashboard links to the IP addresses and the campaigns
    Given I sign in with the scopes "analytics:*"
    When I navigate to "/analytics"
    And I click "All IP Addresses" in the page content
    Then the URL should contain "/analytics/ips"
    When I navigate to "/analytics"
    And I click "Campaigns" in the page content
    Then the URL should be "/analytics/campaigns"

  Scenario: A user without the analytics scope gets the access denied page
    Given I sign in with the scopes "contacts:read"
    When I navigate to "/analytics"
    Then I should see "analytics:read"
    And the page title should contain "Access Denied"

  Scenario: Resetting the analytics asks for a confirmation and reports the result
    Given I sign in with the scopes "analytics:*"
    And resetting analytics succeeds
    When I navigate to "/analytics"
    And I click "Reset All Analytics Data (RAZ)"
    Then the URL should contain "success=Reset+complete"
    And I should see "Reset complete"

  Scenario: A failed reset is reported as an error
    Given I sign in with the scopes "analytics:*"
    And resetting analytics fails
    When I navigate to "/analytics"
    And I click "Reset All Analytics Data (RAZ)"
    Then I should see "Failed to reset analytics"

  Scenario: A user who cannot delete cannot reset
    Given I sign in with the scopes "analytics:read"
    When I navigate to "/analytics"
    Then "Reset All Analytics Data (RAZ)" should be hidden

  # --- Campaigns ---

  Scenario: The campaign list links to the campaign
    Given I sign in with the scopes "analytics:*"
    When I navigate to "/analytics/campaigns"
    Then I should see "Test Campaign"
    When I click "View"
    Then the URL should be "/analytics/campaigns/11111111-1111-1111-1111-111111111111"
    And I should see "A test campaign"
    When I click "Back to Campaigns"
    Then the URL should be "/analytics/campaigns"

  Scenario: Deleting a campaign from its page confirms and reports success
    Given I sign in with the scopes "analytics:*"
    And deleting a campaign succeeds
    When I navigate to "/analytics/campaigns/11111111-1111-1111-1111-111111111111"
    And I click "Delete Campaign"
    Then the URL should contain "/analytics/campaigns?success="
    And I should see "Campaign deleted successfully"

  Scenario: A campaign that cannot be deleted is reported on its page
    Given I sign in with the scopes "analytics:*"
    And deleting a campaign fails
    When I navigate to "/analytics/campaigns/11111111-1111-1111-1111-111111111111"
    And I click "Delete Campaign"
    Then I should see "Failed to delete campaign"

  Scenario: A missing campaign sends the user back to the list
    Given I sign in with the scopes "analytics:*"
    And a campaign does not exist
    When I navigate to "/analytics/campaigns/22222222-2222-2222-2222-222222222222"
    Then the URL should contain "/analytics/campaigns?error="
    And I should see "Campaign not found"

  Scenario: Selected campaigns are deleted in bulk
    Given I sign in with the scopes "analytics:*"
    And bulk deleting campaigns succeeds
    When I navigate to "/analytics/campaigns"
    And I click "css=input[name=campaign_ids]"
    Then I should see "Delete selected (1)"
    When I click "Delete selected (1)"
    Then I should see "Deleted 2 campaigns successfully"

  Scenario: The list can include the inactive campaigns
    Given I sign in with the scopes "analytics:*"
    When I navigate to "/analytics/campaigns"
    And I click "css=#includeInactive"
    Then the URL should be "/analytics/campaigns?include_inactive=true"

  # --- IP addresses ---

  Scenario: The IP list links to the detail of an address
    Given I sign in with the scopes "analytics:*"
    When I navigate to "/analytics/ips"
    And I click "192.168.1.1"
    Then the URL should contain "/analytics/ips/192.168.1.1"
    And I should see "Pages Visited"
    And I should see "New York"

  Scenario: The number of addresses and the period are filters of the list
    Given I sign in with the scopes "analytics:*"
    When I navigate to "/analytics/ips"
    And I select "50 IPs" from "css=#limit"
    Then the URL should contain "limit=50"

  Scenario: An unknown address sends the user back to the list
    Given I sign in with the scopes "analytics:*"
    And IP detail does not exist
    When I navigate to "/analytics/ips/10.0.0.99"
    Then I should see "IP address not found"
