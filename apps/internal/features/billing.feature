Feature: Billing admin dashboard and SaaS management
  As an admin user with billing permissions
  I want to manage SaaS apps, products, prices, customers, and subscriptions
  So that I can administrate the multi-SaaS billing platform

  Background:
    Given I am a super admin

  # ==========================================================================
  # Dashboard
  # ==========================================================================

  @billing-saas
  Scenario: View billing dashboard
    Given the billing SaaS apps list returns data
    When I send a GET request to "/billing"
    Then the response status code should be 200
    And the response should be HTML

  @billing-saas
  Scenario: The dashboard lists inactive SaaS apps too
    Given the billing SaaS apps list returns data
    When I send a GET request to "/billing"
    Then the response status code should be 200
    And the SaaS apps should have been listed with the inactive ones

  @billing-saas
  Scenario: View billing dashboard unauthenticated
    Given I am not authenticated
    When I send a GET request to "/billing"
    Then the response status code should be 302

  # ==========================================================================
  # SaaS Apps - CRUD
  # ==========================================================================

  @billing-saas
  Scenario: View new SaaS app form
    When I send a GET request to "/billing/saas/new"
    Then the response status code should be 200
    And the response should be HTML

  @billing-saas
  Scenario: Create a new SaaS app successfully
    Given creating a SaaS app succeeds
    When I send a POST request to "/billing/saas/new" with form data
      | field          | value                        |
      | name           | My SaaS                      |
      | slug           | my-saas                      |
      | description    | A test SaaS app              |
      | webhook_url    | https://example.com/webhook  |
      | webhook_secret | secret123                    |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/billing/saas/"
    And I should be redirected to a URL containing "success="

  @billing-saas
  Scenario: Create a new SaaS app failure
    Given creating a SaaS app fails
    When I send a POST request to "/billing/saas/new" with form data
      | field | value   |
      | name  | Bad App |
      | slug  | bad-app |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+create"

  @billing-saas
  Scenario: View SaaS app detail
    Given a SaaS app exists with id "saas-1"
    When I send a GET request to "/billing/saas/saas-1"
    Then the response status code should be 200
    And the response should be HTML

  @billing-saas
  Scenario: View SaaS app detail not found
    Given a SaaS app does not exist
    When I send a GET request to "/billing/saas/nonexistent"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/billing"
    And I should be redirected to a URL containing "error="

  @billing-saas
  Scenario: View SaaS app edit form
    Given a SaaS app exists with id "saas-1"
    When I send a GET request to "/billing/saas/saas-1/edit"
    Then the response status code should be 200
    And the response should be HTML

  @billing-saas
  Scenario: View SaaS app edit form not found
    Given a SaaS app does not exist
    When I send a GET request to "/billing/saas/nonexistent/edit"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @billing-saas
  Scenario: Update a SaaS app successfully
    Given updating a SaaS app succeeds
    When I send a POST request to "/billing/saas/saas-1/edit" with form data
      | field       | value         |
      | name        | Updated SaaS  |
      | description | Updated desc  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/billing/saas/saas-1"
    And I should be redirected to a URL containing "success="

  @billing-saas
  Scenario: An unticked Active box deactivates the SaaS app
    Given updating a SaaS app succeeds
    When I send a POST request to "/billing/saas/saas-1/edit" with form data
      | field | value        |
      | name  | Updated SaaS |
    Then the response status code should be 303
    And the SaaS app should have been updated as inactive

  @billing-saas
  Scenario: A ticked Active box keeps the SaaS app active
    Given updating a SaaS app succeeds
    When I send a POST request to "/billing/saas/saas-1/edit" with form data
      | field     | value        |
      | name      | Updated SaaS |
      | is_active | true         |
    Then the response status code should be 303
    And the SaaS app should have been updated as active

  @billing-saas
  Scenario: Update a SaaS app failure
    Given updating a SaaS app fails
    When I send a POST request to "/billing/saas/saas-1/edit" with form data
      | field | value       |
      | name  | Updated SaaS |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+update"

  # ==========================================================================
  # Products
  # ==========================================================================

  @billing-products
  Scenario: List products for a SaaS app
    Given a SaaS app exists with id "saas-1"
    And the billing products list returns data for SaaS "saas-1"
    When I send a GET request to "/billing/saas/saas-1/products"
    Then the response status code should be 200
    And the response should be HTML

  @billing-products
  Scenario: List products when SaaS app not found
    Given a SaaS app does not exist
    When I send a GET request to "/billing/saas/nonexistent/products"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @billing-products
  Scenario: View new product form
    Given a SaaS app exists with id "saas-1"
    When I send a GET request to "/billing/saas/saas-1/products/new"
    Then the response status code should be 200
    And the response should be HTML

  @billing-products
  Scenario: View new product form when SaaS not found
    Given a SaaS app does not exist
    When I send a GET request to "/billing/saas/nonexistent/products/new"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @billing-products
  Scenario: Create a product successfully
    Given creating a billing product succeeds for SaaS "saas-1"
    When I send a POST request to "/billing/saas/saas-1/products/new" with form data
      | field         | value          |
      | name          | Pro Plan       |
      | description   | The pro plan   |
      | slug          | pro-plan       |
      | sort_order    | 1              |
      | features_json | ["Feature A"]  |
      | limits_json   | {}             |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/billing/saas/saas-1/products/"
    And I should be redirected to a URL containing "success="

  @billing-products
  Scenario: Create a product failure
    Given creating a billing product fails for SaaS "saas-1"
    When I send a POST request to "/billing/saas/saas-1/products/new" with form data
      | field | value    |
      | name  | Bad Plan |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+create+product"

  @billing-products
  Scenario: View product detail
    Given a SaaS app exists with id "saas-1"
    And a billing product exists with id "prod-1" for SaaS "saas-1"
    When I send a GET request to "/billing/saas/saas-1/products/prod-1"
    Then the response status code should be 200
    And the response should be HTML

  @billing-products
  Scenario: View product detail when SaaS not found
    Given a SaaS app does not exist
    When I send a GET request to "/billing/saas/nonexistent/products/prod-1"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @billing-products
  Scenario: View product detail when product not found
    Given a SaaS app exists with id "saas-1"
    And a billing product does not exist for SaaS "saas-1"
    When I send a GET request to "/billing/saas/saas-1/products/nonexistent"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Product+not+found"

  @billing-products
  Scenario: View product edit form
    Given a SaaS app exists with id "saas-1"
    And a billing product exists with id "prod-1" for SaaS "saas-1"
    When I send a GET request to "/billing/saas/saas-1/products/prod-1/edit"
    Then the response status code should be 200
    And the response should be HTML

  @billing-products
  Scenario: Update a product successfully
    Given updating a billing product succeeds for SaaS "saas-1"
    When I send a POST request to "/billing/saas/saas-1/products/prod-1/edit" with form data
      | field         | value           |
      | name          | Updated Plan    |
      | description   | Updated desc    |
      | slug          | updated-plan    |
      | sort_order    | 2               |
      | features_json | ["Feature B"]   |
      | limits_json   | {}              |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/billing/saas/saas-1/products/prod-1"
    And I should be redirected to a URL containing "success="

  @billing-products
  Scenario: Update a product failure
    Given updating a billing product fails for SaaS "saas-1"
    When I send a POST request to "/billing/saas/saas-1/products/prod-1/edit" with form data
      | field | value        |
      | name  | Updated Plan |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+update+product"

  # ==========================================================================
  # Prices
  # ==========================================================================

  @billing-prices
  Scenario: View new price form
    Given a SaaS app exists with id "saas-1"
    And a billing product exists with id "prod-1" for SaaS "saas-1"
    When I send a GET request to "/billing/saas/saas-1/products/prod-1/prices/new"
    Then the response status code should be 200
    And the response should be HTML

  @billing-prices
  Scenario: View new price form when resource not found
    Given a SaaS app does not exist
    When I send a GET request to "/billing/saas/nonexistent/products/prod-1/prices/new"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @billing-prices
  Scenario: Create a price successfully
    Given creating a billing price succeeds for SaaS "saas-1" product "prod-1"
    When I send a POST request to "/billing/saas/saas-1/products/prod-1/prices/new" with form data
      | field              | value     |
      | unit_amount        | 1999      |
      | currency           | eur       |
      | billing_type       | recurring |
      | recurring_interval | month     |
      | usage_type         | licensed  |
      | nickname           | Monthly   |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/billing/saas/saas-1/products/prod-1"
    And I should be redirected to a URL containing "success="

  @billing-prices
  Scenario: Create a price and leave the currency and interval to the billing service
    Given creating a billing price succeeds for SaaS "saas-1" product "prod-1"
    When I send a POST request to "/billing/saas/saas-1/products/prod-1/prices/new" with form data
      | field        | value     |
      | unit_amount  | 1999      |
      | billing_type | recurring |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success="
    And the billing price should have been created with the service defaults

  @billing-prices
  Scenario: Create a price failure
    Given creating a billing price fails for SaaS "saas-1" product "prod-1"
    When I send a POST request to "/billing/saas/saas-1/products/prod-1/prices/new" with form data
      | field       | value |
      | unit_amount | 1999  |
      | currency    | eur   |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+create+price"

  @billing-prices
  Scenario: Toggle price active status
    Given toggling a billing price succeeds for SaaS "saas-1" product "prod-1" price "price-1"
    When I send a POST request to "/billing/saas/saas-1/products/prod-1/prices/price-1/toggle"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/billing/saas/saas-1/products/prod-1"

  @billing-prices
  Scenario: Toggle price when price not found
    Given toggling a billing price fails because price not found for SaaS "saas-1" product "prod-1"
    When I send a POST request to "/billing/saas/saas-1/products/prod-1/prices/nonexistent/toggle"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Price+not+found"

  # ==========================================================================
  # Customers
  # ==========================================================================

  @billing-customers
  Scenario: List customers for a SaaS app
    Given a SaaS app exists with id "saas-1"
    And the billing customers list returns data for SaaS "saas-1"
    When I send a GET request to "/billing/saas/saas-1/customers"
    Then the response status code should be 200
    And the response should be HTML

  @billing-customers
  Scenario: List customers when SaaS not found
    Given a SaaS app does not exist
    When I send a GET request to "/billing/saas/nonexistent/customers"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @billing-customers
  Scenario: View customer detail
    Given a SaaS app exists with id "saas-1"
    And a billing customer exists with id "cust-1" for SaaS "saas-1"
    When I send a GET request to "/billing/saas/saas-1/customers/cust-1"
    Then the response status code should be 200
    And the response should be HTML

  @billing-customers
  Scenario: View customer detail when SaaS not found
    Given a SaaS app does not exist
    When I send a GET request to "/billing/saas/nonexistent/customers/cust-1"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @billing-customers
  Scenario: View customer detail when customer not found
    Given a SaaS app exists with id "saas-1"
    And a billing customer does not exist for SaaS "saas-1"
    When I send a GET request to "/billing/saas/saas-1/customers/nonexistent"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Customer+not+found"

  @billing-customers
  Scenario: Redirect to customer portal
    Given the SaaS app "saas-1" accepts the return URL "https://app.example.test"
    And a billing customer portal URL exists for SaaS "saas-1" customer "cust-1"
    When I send a POST request to "/billing/saas/saas-1/customers/cust-1/portal"
    Then the response status code should be 303
    And I should be redirected to a URL containing "https://billing.stripe.com/portal"
    And the billing portal should have been requested with the return URL "https://app.example.test"

  @billing-customers
  Scenario: Customer portal needs a return URL the SaaS app accepts
    Given the SaaS app "saas-1" has no checkout URL allow-list
    When I send a POST request to "/billing/saas/saas-1/customers/cust-1/portal"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=No+return+URL"
    And no billing portal should have been requested

  @billing-customers
  Scenario: Customer portal redirect failure
    Given the SaaS app "saas-1" accepts the return URL "https://app.example.test"
    And a billing customer portal fails for SaaS "saas-1" customer "cust-1"
    When I send a POST request to "/billing/saas/saas-1/customers/cust-1/portal"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+create+portal"

  # ==========================================================================
  # Subscriptions
  # ==========================================================================

  @billing-subscriptions
  Scenario: List subscriptions for a SaaS app
    Given a SaaS app exists with id "saas-1"
    And the billing subscriptions list returns data for SaaS "saas-1"
    When I send a GET request to "/billing/saas/saas-1/subscriptions"
    Then the response status code should be 200
    And the response should be HTML

  @billing-subscriptions
  Scenario: List subscriptions when SaaS not found
    Given a SaaS app does not exist
    When I send a GET request to "/billing/saas/nonexistent/subscriptions"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @billing-subscriptions
  Scenario: View subscription detail
    Given a SaaS app exists with id "saas-1"
    And a billing subscription exists with id "sub-1" for SaaS "saas-1"
    When I send a GET request to "/billing/saas/saas-1/subscriptions/sub-1"
    Then the response status code should be 200
    And the response should be HTML

  @billing-subscriptions
  Scenario: View subscription detail when SaaS not found
    Given a SaaS app does not exist
    When I send a GET request to "/billing/saas/nonexistent/subscriptions/sub-1"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @billing-subscriptions
  Scenario: View subscription detail when subscription not found
    Given a SaaS app exists with id "saas-1"
    And a billing subscription does not exist for SaaS "saas-1"
    When I send a GET request to "/billing/saas/saas-1/subscriptions/nonexistent"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Subscription+not+found"

  @billing-subscriptions
  Scenario: Cancel subscription successfully
    Given canceling a billing subscription succeeds for SaaS "saas-1" subscription "sub-1"
    When I send a POST request to "/billing/saas/saas-1/subscriptions/sub-1/cancel"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/billing/saas/saas-1/subscriptions/sub-1"
    And I should be redirected to a URL containing "success="

  @billing-subscriptions
  Scenario: Cancel subscription failure
    Given canceling a billing subscription fails for SaaS "saas-1" subscription "sub-1"
    When I send a POST request to "/billing/saas/saas-1/subscriptions/sub-1/cancel"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+cancel"

  @billing-subscriptions
  Scenario: Reactivate subscription successfully
    Given reactivating a billing subscription succeeds for SaaS "saas-1" subscription "sub-1"
    When I send a POST request to "/billing/saas/saas-1/subscriptions/sub-1/reactivate"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Subscription+reactivated"
    And the billing subscription "sub-1" should have been reactivated

  @billing-subscriptions
  Scenario: Reactivate subscription failure
    Given reactivating a billing subscription fails for SaaS "saas-1" subscription "sub-1"
    When I send a POST request to "/billing/saas/saas-1/subscriptions/sub-1/reactivate"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+reactivate"

  @billing-subscriptions
  Scenario: Sync subscription successfully
    Given syncing a billing subscription succeeds for SaaS "saas-1" subscription "sub-1"
    When I send a POST request to "/billing/saas/saas-1/subscriptions/sub-1/sync"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Subscription+synced"

  @billing-subscriptions
  Scenario: Sync subscription failure
    Given syncing a billing subscription fails for SaaS "saas-1" subscription "sub-1"
    When I send a POST request to "/billing/saas/saas-1/subscriptions/sub-1/sync"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+sync"
