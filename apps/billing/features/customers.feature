Feature: Platform - Customer Management
  Authenticated users can manage customers within a SaaS app.

  Background:
    Given I am authenticated
    And a SaaS app "Customer Test App" with slug "cust-test" exists

  Scenario: Create a customer
    When I send a POST to "/platform/{saas_id}/customers" with
      """
      {
        "external_id": "user_001",
        "email": "john@example.com",
        "name": "John Doe"
      }
      """
    Then the response status should be 201
    And the response JSON "email" should be "john@example.com"
    And the response JSON "external_id" should be "user_001"
    And the response JSON should contain "id"
    And the response JSON should contain "stripe_customer_id"

  Scenario: Create a customer with duplicate external_id returns 409
    Given a customer "user_dup" exists for the SaaS app
    When I send a POST to "/platform/{saas_id}/customers" with
      """
      {
        "external_id": "user_dup",
        "email": "dup@example.com"
      }
      """
    Then the response status should be 409

  Scenario: List customers
    Given a customer "user_list_1" exists for the SaaS app
    Given a customer "user_list_2" exists for the SaaS app
    When I send a GET to "/platform/{saas_id}/customers"
    Then the response status should be 200
    And the response JSON should be a list of 2 items

  Scenario: Get a customer by ID
    Given a customer "user_get" exists for the SaaS app
    When I send a GET to "/platform/{saas_id}/customers/{customer_id}"
    Then the response status should be 200
    And the response JSON "external_id" should be "user_get"

  Scenario: Update a customer
    Given a customer "user_upd" exists for the SaaS app
    When I send a PATCH to "/platform/{saas_id}/customers/{customer_id}" with
      """
      {
        "name": "Updated Name"
      }
      """
    Then the response status should be 200
    And the response JSON "name" should be "Updated Name"

  Scenario: Get non-existent customer returns 404
    When I send a GET to "/platform/{saas_id}/customers/00000000-0000-0000-0000-000000000000"
    Then the response status should be 404

  Scenario: Get customer portal URL
    Given a customer "user_portal" exists for the SaaS app
    When I send a GET to "/platform/{saas_id}/customers/{customer_id}/portal?return_url=https://example.com"
    Then the response status should be 200
    And the response JSON should contain "url"

  Scenario: The customer portal refuses a return URL outside the allow-list
    Given a customer "user_portal_blocked" exists for the SaaS app
    When I send a GET to "/platform/{saas_id}/customers/{customer_id}/portal?return_url=https://evil.test"
    Then the response status should be 422
