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
