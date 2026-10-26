Feature: OAuth client bindings of the billing SaaS apps
  As an administrator of the billing platform
  I want to choose which OAuth clients may act on each SaaS app
  So that applications sharing the billing service cannot reach each other's data

  Background:
    Given I am a super admin

  # ==========================================================================
  # Listing
  # ==========================================================================

  @billing-clients
  Scenario: The SaaS app page lists the bound OAuth clients
    Given the SaaS app "saas-1" is bound to the OAuth clients "client-a, client-b"
    When I send a GET request to "/billing/saas/saas-1"
    Then the response status code should be 200
    And the response should contain "OAuth clients"
    And the response should contain "client-a"
    And the response should contain "client-b"
    And the response should contain "/billing/saas/saas-1/clients/unbind"

  @billing-clients
  Scenario: The SaaS app page says when no OAuth client is bound
    Given the SaaS app "saas-1" is bound to no OAuth client
    When I send a GET request to "/billing/saas/saas-1"
    Then the response status code should be 200
    And the response should contain "No client bound yet."

  @billing-clients
  Scenario: The bound clients are hidden from users without the admin scope
    Given I am authenticated with scopes "billing:read billing:write"
    And the SaaS app "saas-1" is bound to the OAuth clients "client-a"
    When I send a GET request to "/billing/saas/saas-1"
    Then the response status code should be 200
    And the response should not contain "OAuth clients"
    And the response should not contain "client-a"
    And the OAuth clients of the SaaS app should not have been fetched

  # ==========================================================================
  # Binding
  # ==========================================================================

  @billing-clients
  Scenario: Bind an OAuth client to a SaaS app
    Given binding an OAuth client succeeds
    When I send a POST request to "/billing/saas/saas-1/clients" with form data
      | field     | value    |
      | client_id | client-a |
    Then the response status code should be 303
    And I should be redirected to "/billing/saas/saas-1?success=Client+bound"
    And the OAuth client "client-a" should have been bound to the SaaS app "saas-1"

  @billing-clients
  Scenario: Binding an OAuth client can fail
    Given binding an OAuth client fails
    When I send a POST request to "/billing/saas/saas-1/clients" with form data
      | field     | value    |
      | client_id | client-a |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+bind+client"

  @billing-clients
  Scenario: A client id with spaces is not bound
    Given binding an OAuth client succeeds
    When I send a POST request to "/billing/saas/saas-1/clients" with form data
      | field     | value     |
      | client_id | two words |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="
    And no OAuth client should have been bound

  @billing-clients
  Scenario: Binding needs the billing admin scope
    Given I am authenticated with scopes "billing:read billing:write"
    And binding an OAuth client succeeds
    When I send a POST request to "/billing/saas/saas-1/clients" with form data
      | field     | value    |
      | client_id | client-a |
    Then the response status code should be 403
    And no OAuth client should have been bound

  @billing-clients
  Scenario: Binding requires authentication
    Given I am not authenticated
    When I send a POST request to "/billing/saas/saas-1/clients" with form data
      | field     | value    |
      | client_id | client-a |
    Then the response status code should be 302

  # ==========================================================================
  # Unbinding
  # ==========================================================================

  @billing-clients
  Scenario: Unbind an OAuth client from a SaaS app
    Given unbinding an OAuth client succeeds
    When I send a POST request to "/billing/saas/saas-1/clients/unbind" with form data
      | field     | value    |
      | client_id | client-a |
    Then the response status code should be 303
    And I should be redirected to "/billing/saas/saas-1?success=Client+unbound"
    And the OAuth client "client-a" should have been unbound from the SaaS app "saas-1"

  @billing-clients
  Scenario: Unbinding an OAuth client can fail
    Given unbinding an OAuth client fails
    When I send a POST request to "/billing/saas/saas-1/clients/unbind" with form data
      | field     | value    |
      | client_id | client-a |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+unbind+client"
