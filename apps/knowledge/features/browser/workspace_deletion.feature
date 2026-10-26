@browser
Feature: Workspace deletion flow in a browser
  As the owner of a workspace
  I want to delete it after a confirmation by email
  So that nobody can destroy my data by mistake

  Background:
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And the workspace "Acme" contains the collection "Handbook"
    And the collection "Handbook" contains the document "Alpha note"

  Scenario: The owner asks for the deletion and gets an email to confirm it
    Given I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/settings"
    And I click "Delete Workspace"
    And I fill "Type workspace name to confirm" with "Acme"
    And I click "Send Confirmation Email"
    Then I should see "Confirmation Email Sent"
    And "alice@example.test" received the deletion confirmation for the workspace "Acme"
    And the workspace "Acme" should exist on the "free" plan

  Scenario: The name of the workspace has to be typed exactly
    Given I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/settings"
    And I click "Delete Workspace"
    And I fill "Type workspace name to confirm" with "Acme Corp"
    And I click "Send Confirmation Email"
    Then I should see "Organization name does not match"
    And no deletion email was sent

  Scenario: The deletion is carried out from the link of the email
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Beta" on the "free" plan
    And I have signed in as "Alice" through the identity provider
    And I request the deletion of the workspace "Acme"
    When I open the deletion link sent to "alice@example.test"
    Then I should see "Confirm Workspace Deletion"
    When I click "Yes, Delete Workspace"
    Then the URL should contain "/dashboard"
    And the workspace "Acme" should have been removed from the database
    And "alice@example.test" received the notice that the workspace "Acme" was deleted
    And I should see "Beta"
    And I should not see "Acme"

  Scenario: Deleting the only workspace signs the owner out
    Given I have signed in as "Alice" through the identity provider
    And I request the deletion of the workspace "Acme"
    When I open the deletion link sent to "alice@example.test"
    And I click "Yes, Delete Workspace"
    Then the URL should be "/"
    And the workspace "Acme" should have been removed from the database
    And the browser should not hold the cookie "access_token"

  Scenario: A workspace with a subscription is deleted at the end of the period
    Given the billing service holds the subscription "sub_1" of the workspace until the end of the period
    And I have signed in as "Alice" through the identity provider
    And I request the deletion of the workspace "Acme"
    When I open the deletion link sent to "alice@example.test"
    And I click "Yes, Delete Workspace"
    Then I should see "Deletion Scheduled"
    And the billing service cancelled the subscription "sub_1" at the end of the period
    And "alice@example.test" received the notice that the deletion of "Acme" is scheduled
    And the workspace "Acme" should exist on the "free" plan

  Scenario: A link that is not valid is reported
    Given I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/delete/confirm/not-a-token"
    Then I should see "Deletion request not found"
    When I click "Back to Dashboard"
    Then the URL should be "/dashboard"

  Scenario: A link used twice is reported
    Given "Alice" owns the workspace "Beta" on the "free" plan
    And I have signed in as "Alice" through the identity provider
    And I request the deletion of the workspace "Acme"
    When I open the deletion link sent to "alice@example.test"
    And I click "Yes, Delete Workspace"
    And I open the deletion link sent to "alice@example.test"
    Then I should see "Deletion request not found"

  Scenario: An administrator cannot delete the workspace
    Given a user "Bob" who holds every knowledge scope
    And "Bob" administers the workspace "Acme" on the "free" plan
    And I have signed in as "Bob" through the identity provider
    When I navigate to "/tenants/settings"
    Then I should see "Only the workspace owner can delete this workspace."
    And "css=button[disabled]" should be visible

  Scenario: The deletion pages only lead to pages that exist
    Given I have signed in as "Alice" through the identity provider
    And I request the deletion of the workspace "Acme"
    Then every link of the page leads to a page of the application
    When I open the deletion link sent to "alice@example.test"
    Then every link of the page leads to a page of the application
    When I navigate to "/tenants/delete/confirm/not-a-token"
    Then every link of the page leads to a page of the application
