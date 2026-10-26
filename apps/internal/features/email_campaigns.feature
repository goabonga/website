Feature: Email campaigns management
  As an admin user with email campaign permissions
  I want to create, view, edit, send, and delete email campaigns
  So that I can manage bulk email communications

  Background:
    Given I am a super admin

  # ==========================================================================
  # List campaigns
  # ==========================================================================

  @email-campaigns
  Scenario: List email campaigns
    Given the campaigns API returns a list of campaigns
    When I send a GET request to "/email-campaigns"
    Then the response status code should be 200
    And the response should be HTML

  @email-campaigns
  Scenario: List email campaigns unauthenticated
    Given I am not authenticated
    When I send a GET request to "/email-campaigns"
    Then the response status code should be 302

  @email-campaigns
  Scenario: List email campaigns with search filter
    Given the campaigns API returns a list of campaigns
    When I send a GET request to "/email-campaigns?search=newsletter"
    Then the response status code should be 200
    And the response should be HTML

  @email-campaigns
  Scenario: List email campaigns with status filter
    Given the campaigns API returns a list of campaigns
    When I send a GET request to "/email-campaigns?status=draft"
    Then the response status code should be 200
    And the response should be HTML

  # ==========================================================================
  # New campaign form
  # ==========================================================================

  @email-campaigns
  Scenario: View new campaign form
    Given the campaigns API returns templates and groups for the form
    When I send a GET request to "/email-campaigns/new"
    Then the response status code should be 200
    And the response should be HTML

  # ==========================================================================
  # Create campaign
  # ==========================================================================

  @email-campaigns
  Scenario: Create a new campaign successfully
    Given creating a campaign via API succeeds
    When I send a POST request to "/email-campaigns/new" with form data
      | field       | value           |
      | name        | My Campaign     |
      | description | Test campaign   |
      | template_id | 1               |
      | group_id    | 1               |
      | provider    | ses             |
      | from_name   | Sender          |
      | from_email  | noreply@test.com|
      | reply_to    | reply@test.com  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/email-campaigns/"
    And I should be redirected to a URL containing "success=Campaign+created"

  @email-campaigns
  Scenario: Create a new campaign failure
    Given creating a campaign via API fails
    When I send a POST request to "/email-campaigns/new" with form data
      | field       | value           |
      | name        | Bad Campaign    |
      | template_id | 1               |
      | group_id    | 1               |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+create+campaign"

  # ==========================================================================
  # Campaign detail
  # ==========================================================================

  @email-campaigns
  Scenario: View campaign detail
    Given a campaign exists via API with id 1
    When I send a GET request to "/email-campaigns/1"
    Then the response status code should be 200
    And the response should be HTML

  @email-campaigns
  Scenario: View campaign detail not found
    Given a campaign does not exist via API
    When I send a GET request to "/email-campaigns/999"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Campaign+not+found"

  # ==========================================================================
  # Edit campaign
  # ==========================================================================

  @email-campaigns
  Scenario: View campaign edit form
    Given a draft campaign exists via API with id 1
    And the campaigns API returns templates and groups for the form
    When I send a GET request to "/email-campaigns/1/edit"
    Then the response status code should be 200
    And the response should be HTML

  @email-campaigns
  Scenario: View campaign edit form for sending campaign is blocked
    Given a sending campaign exists via API with id 2
    When I send a GET request to "/email-campaigns/2/edit"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Cannot+edit+campaign"

  @email-campaigns
  Scenario: Update a campaign successfully
    Given a draft campaign exists via API with id 1
    And updating a campaign via API succeeds
    When I send a POST request to "/email-campaigns/1/edit" with form data
      | field       | value              |
      | name        | Updated Campaign   |
      | description | Updated desc       |
      | template_id | 1                  |
      | group_id    | 1                  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/email-campaigns/1"
    And I should be redirected to a URL containing "success=Campaign+updated"

  @email-campaigns
  Scenario: Update a campaign failure
    Given a draft campaign exists via API with id 1
    And updating a campaign via API fails
    When I send a POST request to "/email-campaigns/1/edit" with form data
      | field       | value              |
      | name        | Updated Campaign   |
      | template_id | 1                  |
      | group_id    | 1                  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+update+campaign"

  # ==========================================================================
  # Send / Pause / Resume
  # ==========================================================================

  @email-campaigns
  Scenario: Send a draft campaign
    Given a draft campaign exists via API with id 1
    And sending a campaign via API succeeds
    When I send a POST request to "/email-campaigns/1/send"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Campaign+sending+started"

  @email-campaigns
  Scenario: Send a campaign that is not in draft or scheduled status
    Given a sending campaign exists via API with id 2
    When I send a POST request to "/email-campaigns/2/send"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Campaign+cannot+be+sent"

  @email-campaigns
  Scenario: Pause a sending campaign
    Given a sending campaign exists via API with id 2
    And pausing a campaign via API succeeds
    When I send a POST request to "/email-campaigns/2/pause"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Campaign+paused"

  @email-campaigns
  Scenario: Pause a campaign that is not sending
    Given a draft campaign exists via API with id 1
    When I send a POST request to "/email-campaigns/1/pause"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Campaign+is+not+currently+sending"

  @email-campaigns
  Scenario: Resume a paused campaign
    Given a paused campaign exists via API with id 3
    And resuming a campaign via API succeeds
    When I send a POST request to "/email-campaigns/3/resume"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Campaign+resumed"

  @email-campaigns
  Scenario: Resume a campaign that is not paused
    Given a draft campaign exists via API with id 1
    When I send a POST request to "/email-campaigns/1/resume"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Campaign+is+not+paused"

  # ==========================================================================
  # Delete campaign
  # ==========================================================================

  @email-campaigns
  Scenario: Delete a draft campaign
    Given a draft campaign exists via API with id 1
    And deleting a campaign via API succeeds
    When I send a POST request to "/email-campaigns/1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Campaign+deleted"

  @email-campaigns
  Scenario: Delete a sending campaign is blocked
    Given a sending campaign exists via API with id 2
    When I send a POST request to "/email-campaigns/2/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Cannot+delete+campaign+while+sending"

  @email-campaigns
  Scenario: Delete a campaign not found
    Given a campaign does not exist via API
    When I send a POST request to "/email-campaigns/999/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Campaign+not+found"

  # ==========================================================================
  # Bulk delete
  # ==========================================================================

  @email-campaigns
  Scenario: Bulk delete campaigns
    Given bulk delete campaigns via API deletes 2 campaigns
    When I send a POST request to "/email-campaigns/bulk-delete" with form data
      | field        | value |
      | campaign_ids | 1     |
      | campaign_ids | 2     |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Deleted+2"

  @email-campaigns
  Scenario: Bulk delete with no selection
    When I send a POST request to "/email-campaigns/bulk-delete" with form data
      | field | value |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=No+campaigns+selected"

  # ==========================================================================
  # Stats JSON endpoint
  # ==========================================================================

  @email-campaigns
  Scenario: Get campaign stats JSON
    Given a campaign with stats exists via API with id 1
    When I send a GET request to "/email-campaigns/1/stats"
    Then the response status code should be 200
    And the response should be valid JSON
    And the response JSON should have key "status"
    And the response JSON should have key "sent_count"

  @email-campaigns
  Scenario: Get campaign stats for non-existent campaign
    Given a campaign does not exist via API
    When I send a GET request to "/email-campaigns/999/stats"
    Then the response status code should be 404
    And the response should be valid JSON

  # --- Sidebar ---

  Scenario: Sidebar on the email campaigns list
    Given I am authenticated with only the scopes "email_campaigns:* vpn:admin billing:read" granted by token exchange
    And the campaigns API returns a list of campaigns
    When I send a GET request to "/email-campaigns"
    Then the response status code should be 200
    And the active sidebar link should be "/email-campaigns"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the new email campaign form
    Given I am authenticated with only the scopes "email_campaigns:* vpn:admin billing:read" granted by token exchange
    And the campaigns API returns templates and groups for the form
    When I send a GET request to "/email-campaigns/new"
    Then the response status code should be 200
    And the active sidebar link should be "/email-campaigns"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the email campaign detail
    Given I am authenticated with only the scopes "email_campaigns:* vpn:admin billing:read" granted by token exchange
    And a campaign exists via API with id 1
    When I send a GET request to "/email-campaigns/1"
    Then the response status code should be 200
    And the active sidebar link should be "/email-campaigns"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the email campaign edit form
    Given I am authenticated with only the scopes "email_campaigns:* vpn:admin billing:read" granted by token exchange
    And a draft campaign exists via API with id 1
    And the campaigns API returns templates and groups for the form
    When I send a GET request to "/email-campaigns/1/edit"
    Then the response status code should be 200
    And the active sidebar link should be "/email-campaigns"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario Outline: Sidebar gated links follow the scopes on the email campaigns list
    Given I am authenticated with only the scopes "<scopes>" granted by token exchange
    And the campaigns API returns a list of campaigns
    When I send a GET request to "/email-campaigns"
    Then the response status code should be 200
    And the sidebar link to "/vpn/sessions" should be <vpn>
    And the sidebar link to "/billing" should be <billing>

    Examples:
      | scopes                                   | vpn     | billing |
      | email_campaigns:*                        | hidden  | hidden  |
      | email_campaigns:* vpn:admin              | visible | hidden  |
      | email_campaigns:* billing:read           | hidden  | visible |
      | email_campaigns:* vpn:admin billing:read | visible | visible |
      | *                                        | visible | visible |
