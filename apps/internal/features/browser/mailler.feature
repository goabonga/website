@browser
Feature: Mailler statistics in a browser
  As an operator with the mailler permissions
  I want to follow the email statistics and browse the sent emails
  So that I can monitor the email delivery system

  Background:
    Given the mailler stats returns data
    And the mailler emails list returns data
    And an email exists with id "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

  # --- Dashboard ---

  Scenario: The dashboard shows the totals and the providers
    Given I sign in with the scopes "mailler:*"
    When I navigate to "/mailler"
    Then the page title should be "Mailler Dashboard - Internal Admin"
    And I should see "Daily Email Volume"
    And I should see "DELIVERY RATE"
    And I should see "Statistics by Provider"
    And I should see "2024-01-15"
    And the sidebar menu should highlight only "Mailler Stats"
    And the browser should report no errors

  Scenario: A user without the mailler scope gets the access denied page
    Given I sign in with the scopes "contacts:read"
    When I navigate to "/mailler"
    Then the page title should contain "Access Denied"
    And I should see "mailler:read"

  Scenario: An anonymous visitor comes back to the dashboard after the login
    Given a user holding the scopes "mailler:*" exists at the provider
    When I navigate to "/mailler?days=7&provider=ses"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/mailler?days=7&provider=ses"

  Scenario: Changing the period reloads the dashboard
    Given I sign in with the scopes "mailler:*"
    When I navigate to "/mailler"
    And I select "Last 7 days" from "css=#days"
    Then the URL should contain "days=7"

  Scenario: Choosing a provider restricts the statistics to it
    Given I sign in with the scopes "mailler:*"
    When I navigate to "/mailler"
    And I select "Ses" from "css=#provider"
    Then the URL should contain "provider=ses"

  Scenario: The dashboard links to the list of emails
    Given I sign in with the scopes "mailler:*"
    When I navigate to "/mailler"
    And I click "View All Emails →"
    Then the URL should be "/mailler/emails"

  # --- Emails ---

  Scenario: The emails are listed with their status
    Given I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/emails"
    Then the page title should be "Emails - Mailler - Internal Admin"
    And I should see "user@example.com"
    And I should see "Test Email"
    And I should see "Showing 1 of 1 emails"
    And the sidebar menu should highlight only "Mailler Stats"

  Scenario: The emails are filtered by provider and by status
    Given I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/emails"
    And I select "Ses" from "css=#provider"
    Then the URL should contain "provider=ses"
    When I select "Delivered" from "css=#status"
    Then the URL should contain "status=delivered"
    And the URL should contain "provider=ses"
    And the mailler service should have been asked for the emails of the provider "ses"

  Scenario: The number of emails per page can be changed
    Given I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/emails"
    And I select "50" from "css=#page_size"
    Then the URL should contain "page_size=50"

  Scenario: The emails are paginated
    Given the mailler emails list has 3 pages
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/emails"
    Then I should see "Page 1 of 3"
    When I click "Next ›"
    Then the URL should contain "page=2"
    When I click "Last »"
    Then the URL should contain "page=3"

  Scenario: The filters are kept when moving to another page
    Given the mailler emails list has 3 pages
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/emails?provider=ses&status=delivered"
    And I click "Next ›"
    Then the URL should contain "provider=ses"
    And the URL should contain "status=delivered"
    And the URL should contain "page=2"

  # --- Email detail ---

  Scenario: The list leads to the detail of an email
    Given I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/emails"
    And I click "View"
    Then the URL should be "/mailler/emails/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    And I should see "ses-msg-001"
    And I should see "TIMELINE"
    When I click "← Back to list"
    Then the URL should be "/mailler/emails"

  Scenario: An email that does not exist sends the user back to the list
    Given an email does not exist
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/emails/aaaaaaaa-bbbb-cccc-dddd-ffffffffffff"
    Then the URL should contain "/mailler/emails?error="
    And I should see "Email not found"

  Scenario: An invalid email id sends the user back to the list
    Given I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/emails/not-a-valid-uuid"
    Then I should see "Invalid email ID"
