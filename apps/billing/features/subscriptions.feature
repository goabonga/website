Feature: Platform - Subscription Management
  Authenticated users can manage subscriptions for customers.

  Background:
    Given I am authenticated
    And a SaaS app "Sub Test App" with slug "sub-test" exists
    And a product "Sub Product" exists for the SaaS app
    And a price "Sub Price" exists for the product
    And a customer "sub_user" exists for the SaaS app

  Scenario: Create a subscription
    When I send a POST to "/platform/{saas_id}/customers/{customer_id}/subscriptions" with
      """
      {
        "price_id": "{price_id}"
      }
      """
    Then the response status should be 201
    And the response JSON should contain "id"
    And the response JSON should contain "stripe_subscription_id"

  Scenario: List subscriptions for a SaaS app
    Given a subscription exists for the customer
    When I send a GET to "/platform/{saas_id}/subscriptions"
    Then the response status should be 200
    And the response JSON should be a non-empty list

  Scenario: List subscriptions for a customer
    Given a subscription exists for the customer
    When I send a GET to "/platform/{saas_id}/customers/{customer_id}/subscriptions"
    Then the response status should be 200
    And the response JSON should be a non-empty list

  Scenario: Get a subscription by ID
    Given a subscription exists for the customer
    When I send a GET to "/platform/{saas_id}/subscriptions/{subscription_id}"
    Then the response status should be 200
    And the response JSON should contain "status"

  Scenario: Get subscription by external_id
    Given a subscription exists for the customer
    When I send a GET to "/platform/{saas_id}/external/sub_user/subscription"
    Then the response status should be 200

  Scenario: Update a subscription
    Given a subscription exists for the customer
    When I send a PATCH to "/platform/{saas_id}/subscriptions/{subscription_id}" with
      """
      {
        "cancel_at_period_end": true
      }
      """
    Then the response status should be 200
    And the response JSON "cancel_at_period_end" should be true

  Scenario: Cancel a subscription at period end
    Given a subscription exists for the customer
    When I send a DELETE to "/platform/{saas_id}/subscriptions/{subscription_id}"
    Then the response status should be 200

  Scenario: Cancel a subscription immediately
    Given a subscription exists for the customer
    When I send a DELETE to "/platform/{saas_id}/subscriptions/{subscription_id}?immediately=true"
    Then the response status should be 200

  Scenario: Sync subscription from Stripe
    Given a subscription exists for the customer
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/sync"
    Then the response status should be 200
    And the response JSON should contain "status"

  Scenario: Preview subscription upgrade
    Given a subscription exists for the customer
    And a second price "Upgrade Price" exists for the product
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/upgrade/preview" with
      """
      {
        "new_price_id": "{new_price_id}"
      }
      """
    Then the response status should be 200
    And the response JSON should contain "current_plan_name"
    And the response JSON should contain "total"

  Scenario: Upgrade subscription to new plan
    Given a subscription exists for the customer
    And a second price "Upgrade Price" exists for the product
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/upgrade" with
      """
      {
        "new_price_id": "{new_price_id}"
      }
      """
    Then the response status should be 200
    And the response JSON should contain "subscription"
    And the response JSON "proration_applied" should be true

  Scenario: Get non-existent subscription returns 404
    When I send a GET to "/platform/{saas_id}/subscriptions/00000000-0000-0000-0000-000000000000"
    Then the response status should be 404
