Feature: Mailler dashboard and email management
  As an admin user with mailler permissions
  I want to view email statistics and browse sent emails
  So that I can monitor the email delivery system

  Background:
    Given I am a super admin

  # --- Dashboard ---

  Scenario: View mailler dashboard
    Given the mailler stats returns data
    When I send a GET request to "/mailler"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View mailler dashboard unauthenticated
    Given I am not authenticated
    When I send a GET request to "/mailler"
    Then the response status code should be 302

  Scenario: View mailler dashboard with provider filter
    Given the mailler stats returns data
    When I send a GET request to "/mailler?provider=ses"
    Then the response status code should be 200
    And the response should be HTML

  # --- Emails list ---

  Scenario: List emails
    Given the mailler emails list returns data
    When I send a GET request to "/mailler/emails"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: List emails with filters
    Given the mailler emails list returns data
    When I send a GET request to "/mailler/emails?provider=ses&status=delivered&page=1"
    Then the response status code should be 200
    And the response should be HTML

  # --- Email detail ---

  Scenario: View email detail when found
    Given an email exists with id "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    When I send a GET request to "/mailler/emails/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View email detail when not found
    Given an email does not exist
    When I send a GET request to "/mailler/emails/aaaaaaaa-bbbb-cccc-dddd-ffffffffffff"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/mailler/emails"
    And I should be redirected to a URL containing "error=Email+not+found"

  Scenario: View email detail with invalid UUID
    When I send a GET request to "/mailler/emails/not-a-valid-uuid"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Invalid+email+ID"

  # --- Sidebar ---

  Scenario: Sidebar on the mailler dashboard
    Given I am authenticated with only the scopes "mailler:* vpn:admin billing:read" granted by token exchange
    And the mailler stats returns data
    When I send a GET request to "/mailler"
    Then the response status code should be 200
    And the active sidebar link should be "/mailler"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the emails list
    Given I am authenticated with only the scopes "mailler:* vpn:admin billing:read" granted by token exchange
    And the mailler emails list returns data
    When I send a GET request to "/mailler/emails"
    Then the response status code should be 200
    And the active sidebar link should be "/mailler"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the email detail
    Given I am authenticated with only the scopes "mailler:* vpn:admin billing:read" granted by token exchange
    And an email exists with id "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    When I send a GET request to "/mailler/emails/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    Then the response status code should be 200
    And the active sidebar link should be "/mailler"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario Outline: Sidebar gated links follow the scopes on the mailler dashboard
    Given I am authenticated with only the scopes "<scopes>" granted by token exchange
    And the mailler stats returns data
    When I send a GET request to "/mailler"
    Then the response status code should be 200
    And the sidebar link to "/vpn/sessions" should be <vpn>
    And the sidebar link to "/billing" should be <billing>

    Examples:
      | scopes                           | vpn     | billing |
      | mailler:*                        | hidden  | hidden  |
      | mailler:* vpn:admin              | visible | hidden  |
      | mailler:* billing:read           | hidden  | visible |
      | mailler:* vpn:admin billing:read | visible | visible |
      | *                                | visible | visible |
