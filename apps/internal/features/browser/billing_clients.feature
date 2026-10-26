@browser
Feature: OAuth client bindings of the billing SaaS apps in a browser
  As an administrator of the billing platform
  I want to choose which OAuth clients may act on each SaaS app
  So that applications sharing the billing service cannot reach each other's data

  Scenario: The page of a SaaS app lists the bound OAuth clients
    Given the SaaS app "saas-1" is bound to the OAuth clients "client-a, client-b"
    And I sign in with the scopes "billing:* billing:admin"
    When I navigate to "/billing/saas/saas-1"
    Then I should see "OAuth clients"
    And I should see "client-a"
    And I should see "client-b"
    And the sidebar menu should highlight only "Billing"

  Scenario: The page says when no OAuth client is bound
    Given the SaaS app "saas-1" is bound to no OAuth client
    And I sign in with the scopes "billing:* billing:admin"
    When I navigate to "/billing/saas/saas-1"
    Then I should see "No client bound yet."

  Scenario: The bound clients are hidden from users without the admin scope
    Given the SaaS app "saas-1" is bound to the OAuth clients "client-a"
    And I sign in with the scopes "billing:read billing:write"
    When I navigate to "/billing/saas/saas-1"
    Then I should see "Test App"
    And I should not see "OAuth clients"
    And I should not see "client-a"
    And the OAuth clients of the SaaS app should not have been fetched

  Scenario: An OAuth client is bound from the page of the SaaS app
    Given the SaaS app "saas-1" is bound to no OAuth client
    And binding an OAuth client succeeds
    And I sign in with the scopes "billing:* billing:admin"
    When I navigate to "/billing/saas/saas-1"
    And I fill "OAuth client ID" with "client-a"
    And I click "Bind client"
    Then the URL should contain "/billing/saas/saas-1?success="
    And I should see "Client bound"
    And the OAuth client "client-a" should have been bound to the SaaS app "saas-1"

  Scenario: Binding an OAuth client can fail
    Given the SaaS app "saas-1" is bound to no OAuth client
    And binding an OAuth client fails
    And I sign in with the scopes "billing:* billing:admin"
    When I navigate to "/billing/saas/saas-1"
    And I fill "OAuth client ID" with "client-a"
    And I click "Bind client"
    Then I should see "Failed to bind client"

  Scenario: A client id with spaces is stopped by the form
    Given the SaaS app "saas-1" is bound to no OAuth client
    And binding an OAuth client succeeds
    And I sign in with the scopes "billing:* billing:admin"
    When I navigate to "/billing/saas/saas-1"
    And I fill "OAuth client ID" with "two words"
    And I click "Bind client"
    Then the URL should be "/billing/saas/saas-1"
    And no OAuth client should have been bound

  Scenario: An OAuth client is unbound from the page of the SaaS app
    Given the SaaS app "saas-1" is bound to the OAuth clients "client-a, client-b"
    And unbinding an OAuth client succeeds
    And I sign in with the scopes "billing:* billing:admin"
    When I navigate to "/billing/saas/saas-1"
    And I click "css=tr:has-text('client-b') button"
    Then the URL should contain "/billing/saas/saas-1?success="
    And I should see "Client unbound"
    And the OAuth client "client-b" should have been unbound from the SaaS app "saas-1"

  Scenario: Unbinding an OAuth client can fail
    Given the SaaS app "saas-1" is bound to the OAuth clients "client-a"
    And unbinding an OAuth client fails
    And I sign in with the scopes "billing:* billing:admin"
    When I navigate to "/billing/saas/saas-1"
    And I click "Unbind"
    Then I should see "Failed to unbind client"
