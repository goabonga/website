Feature: Workspace deletion
  As the owner of a workspace
  I want to delete it after an email confirmation
  So that an accidental click can never destroy my data

  Background:
    Given the workspace database is in memory
    And the billing client is in memory
    And deletion emails are queued in memory

  Scenario: Only the owner can request a deletion
    Given I am an administrator of the workspace "Acme" on the "pro" plan
    When I request the deletion of the workspace typing "Acme"
    Then the response status code should be 403

  Scenario: The workspace name must be typed exactly
    Given I am the owner of the workspace "Acme" on the "pro" plan
    When I request the deletion of the workspace typing "acme-typo"
    Then the response status code should be 200
    And the page should say "name does not match"
    And no deletion request should exist

  Scenario: A confirmed name creates a request and sends the confirmation email
    Given I am the owner of the workspace "Acme" on the "pro" plan
    When I request the deletion of the workspace typing "Acme"
    Then the response status code should be 200
    And a pending deletion request should exist
    And a confirmation email should be queued with a link to the confirmation page

  Scenario: A new request cancels the previous pending one
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And a pending deletion request exists for the workspace
    When I request the deletion of the workspace typing "Acme"
    Then 1 deletion request should be "cancelled"
    And 1 deletion request should be "pending"

  Scenario: The confirmation page shows the workspace to delete
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And a pending deletion request exists for the workspace
    When I open the deletion confirmation page
    Then the response status code should be 200
    And the page should say "Acme"

  Scenario: An unknown confirmation link is reported
    Given I am the owner of the workspace "Acme" on the "pro" plan
    When I open "/organizations/delete/confirm/unknown"
    Then the page should say "Deletion request not found"

  Scenario: An expired confirmation link is reported and marked
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And an expired deletion request exists for the workspace
    When I open the deletion confirmation page
    Then the page should say "Deletion request expired"
    And 1 deletion request should be "expired"

  Scenario: Confirming deletes a workspace without subscription at once
    Given I am the owner of the workspace "Acme" on the "free" plan
    And I also belong to the workspace "Globex"
    And a pending deletion request exists for the workspace
    When I confirm the deletion
    Then the response status code should be 302
    And I should be redirected to "/dashboard?deleted=true"
    And the workspace "Acme" should no longer exist
    And 1 deletion request should be "confirmed"
    And a "deleted" email should be queued

  Scenario: Deleting the last workspace signs the user out
    Given I am the owner of the workspace "Acme" on the "free" plan
    And a pending deletion request exists for the workspace
    When I confirm the deletion
    Then I should be redirected to "/auth/logout?redirect=/"
    And the workspace "Acme" should no longer exist

  Scenario: A paid workspace is scheduled for the end of the billing period
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And the workspace has a subscription "sub_1" renewing in 20 days
    And a pending deletion request exists for the workspace
    When I confirm the deletion
    Then the response status code should be 200
    And the page should say "scheduled"
    And the subscription "sub_1" should have been set to cancel at period end
    And 1 deletion request should be "scheduled"
    And the workspace "Acme" should still exist
    And a "scheduled" email should be queued

  Scenario: Cancelling a scheduled deletion reactivates the subscription
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And the workspace has a subscription "sub_1" renewing in 20 days
    And a scheduled deletion request exists for the workspace
    When I open the cancellation link
    Then the response status code should be 200
    And 1 deletion request should be "cancelled"
    And the subscription "sub_1" should have been reactivated

  Scenario: A cancellation link works only for scheduled deletions
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And a deletion request that was already carried out exists for the workspace
    When I open the cancellation link
    Then the page should say "Cannot cancel"

  Scenario: Deletion pages require a signed-in user
    Given I am not signed in
    When I open "/organizations/delete/confirm/anything"
    Then the response status code should be 302
    And I should be redirected to a URL starting with "/auth/login"
