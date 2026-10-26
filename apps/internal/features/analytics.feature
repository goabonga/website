Feature: Analytics dashboard and campaigns management
  As an admin user with analytics permissions
  I want to view analytics dashboards, manage campaigns, and view IP stats
  So that I can monitor website traffic and marketing performance

  Background:
    Given I am a super admin

  # --- Dashboard ---

  Scenario: View analytics dashboard
    Given the analytics overview returns data
    When I send a GET request to "/analytics"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View analytics dashboard unauthenticated
    Given I am not authenticated
    When I send a GET request to "/analytics"
    Then the response status code should be 302

  Scenario: View analytics dashboard with custom days parameter
    Given the analytics overview returns data
    When I send a GET request to "/analytics?days=7"
    Then the response status code should be 200
    And the response should be HTML

  # --- Campaigns ---

  Scenario: List campaigns
    Given the campaigns list returns data
    When I send a GET request to "/analytics/campaigns"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View campaign detail when found
    Given a campaign exists with id "11111111-1111-1111-1111-111111111111"
    When I send a GET request to "/analytics/campaigns/11111111-1111-1111-1111-111111111111"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View campaign detail when not found
    Given a campaign does not exist
    When I send a GET request to "/analytics/campaigns/22222222-2222-2222-2222-222222222222"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/analytics/campaigns"

  Scenario: Delete campaign successfully
    Given deleting a campaign succeeds
    When I send a POST request to "/analytics/campaigns/11111111-1111-1111-1111-111111111111/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Campaign+deleted"

  Scenario: Delete campaign failure
    Given deleting a campaign fails
    When I send a POST request to "/analytics/campaigns/11111111-1111-1111-1111-111111111111/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+delete"

  Scenario: Bulk delete campaigns
    Given bulk deleting campaigns succeeds
    When I send a POST request to "/analytics/campaigns/bulk-delete" with form data
      | field        | value                                |
      | campaign_ids | 11111111-1111-1111-1111-111111111111 |
      | campaign_ids | 22222222-2222-2222-2222-222222222222 |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Deleted"

  Scenario: Bulk delete with invalid UUIDs
    When I send a POST request to "/analytics/campaigns/bulk-delete" with form data
      | field        | value       |
      | campaign_ids | not-a-uuid  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Invalid+campaign+ID"

  # --- IP Stats ---

  Scenario: View IP stats list
    Given the IP stats returns data
    When I send a GET request to "/analytics/ips"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View IP detail when found
    Given IP detail exists for "192.168.1.1"
    When I send a GET request to "/analytics/ips/192.168.1.1"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View IP detail when not found
    Given IP detail does not exist
    When I send a GET request to "/analytics/ips/10.0.0.99"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/analytics/ips"

  # --- Reset ---

  Scenario: Reset analytics with delete scope
    Given I am authenticated with scope "analytics:delete"
    And resetting analytics succeeds
    When I send a POST request to "/analytics/reset"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Reset+complete"

  Scenario: Reset analytics failure
    Given I am authenticated with scope "analytics:delete"
    And resetting analytics fails
    When I send a POST request to "/analytics/reset"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+reset"
