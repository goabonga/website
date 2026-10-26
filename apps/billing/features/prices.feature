Feature: Platform - Price Management
  Authenticated users can manage billing prices within a product.

  Background:
    Given I am authenticated
    And a SaaS app "Price Test App" with slug "price-test" exists
    And a product "Price Product" exists for the SaaS app

  Scenario: Create a price
    When I send a POST to "/platform/{saas_id}/products/{product_id}/prices" with
      """
      {
        "nickname": "Monthly Pro",
        "currency": "usd",
        "unit_amount": 2999,
        "billing_type": "recurring",
        "recurring_interval": "month",
        "recurring_interval_count": 1,
        "usage_type": "licensed"
      }
      """
    Then the response status should be 201
    And the response JSON "nickname" should be "Monthly Pro"
    And the response JSON "unit_amount" should be "2999"
    And the response JSON should contain "id"
    And the response JSON should contain "stripe_price_id"

  Scenario: A price without currency and interval takes the configured defaults
    When I send a POST to "/platform/{saas_id}/products/{product_id}/prices" with
      """
      {
        "unit_amount": 1000
      }
      """
    Then the response status should be 201
    And the response JSON "currency" should be "usd"
    And the response JSON "recurring_interval" should be "month"

  Scenario: List prices for a product
    Given a price "Starter Monthly" exists for the product
    When I send a GET to "/platform/{saas_id}/products/{product_id}/prices"
    Then the response status should be 200
    And the response JSON should be a non-empty list

  Scenario: Get a price by ID
    Given a price "Lookup Price" exists for the product
    When I send a GET to "/platform/{saas_id}/products/{product_id}/prices/{price_id}"
    Then the response status should be 200
    And the response JSON "nickname" should be "Lookup Price"

  Scenario: Update a price nickname
    Given a price "Old Nickname" exists for the product
    When I send a PATCH to "/platform/{saas_id}/products/{product_id}/prices/{price_id}" with
      """
      {
        "nickname": "New Nickname"
      }
      """
    Then the response status should be 200
    And the response JSON "nickname" should be "New Nickname"

  Scenario: Deactivate a price
    Given a price "Deactivate Me" exists for the product
    When I send a PATCH to "/platform/{saas_id}/products/{product_id}/prices/{price_id}" with
      """
      {
        "is_active": false
      }
      """
    Then the response status should be 200
    And the response JSON "is_active" should be false

  Scenario: Get non-existent price returns 404
    When I send a GET to "/platform/{saas_id}/products/{product_id}/prices/00000000-0000-0000-0000-000000000000"
    Then the response status should be 404

  Scenario: Sync products and prices to Stripe
    Given a SaaS app "Sync App" with slug "sync-test" exists with products and prices
    When I send a POST to "/platform/saas/{saas_id}/sync-stripe"
    Then the response status should be 200
    And the response JSON "products_synced" should be "1"
    And the response JSON "prices_synced" should be "1"
