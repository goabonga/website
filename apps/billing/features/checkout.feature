Feature: Checkout Sessions
  Authenticated users can create Stripe checkout sessions.

  Background:
    Given I am authenticated
    And a SaaS app "Checkout App" with slug "checkout-test" exists
    And a product "Checkout Product" exists for the SaaS app
    And a price "Checkout Price" exists for the product
    And a customer "checkout_user" exists for the SaaS app

  Scenario: Create a checkout session with customer_id
    When I create a checkout session with customer_id
    Then the response status should be 200
    And the response JSON should contain "session_id"
    And the response JSON should contain "url"

  Scenario: Create a checkout session with external_id
    When I create a checkout session with external_id "checkout_user"
    Then the response status should be 200
    And the response JSON should contain "session_id"

  Scenario: Auto-create customer during checkout
    When I create a checkout session with new external_id "new_user" and email "new@example.com"
    Then the response status should be 200
    And the response JSON should contain "session_id"

  Scenario: Checkout with non-existent customer returns 404
    When I create a checkout session with external_id "ghost_user"
    Then the response status should be 404

  Scenario: Checkout with non-existent price returns 404
    When I create a checkout session with non-existent price
    Then the response status should be 404

  Scenario: Checkout with a price of another SaaS app returns 404
    Given another SaaS app "Foreign App" with slug "foreign-checkout" has a price
    When I create a checkout session with customer_id and the foreign price
    Then the response status should be 404

  Scenario: Checkout metadata cannot override the SaaS identifier
    Given the real Stripe service talks to a mocked Stripe SDK
    When I create a checkout session with metadata "saas_id=forged"
    Then the response status should be 200
    And the Stripe SDK checkout session should carry the SaaS identifier of the SaaS app

  Scenario: Checkout with a success URL outside the allow-list returns 422
    When I create a checkout session with success URL "https://evil.test/done"
    Then the response status should be 422

  Scenario: Checkout for a SaaS app without allow-list returns 422
    Given the SaaS app has no checkout URL allow-list
    When I create a checkout session with customer_id
    Then the response status should be 422

  Scenario: The SaaS app branding customizes the hosted page
    Given the SaaS app has the branding locale "fr"
    When I create a checkout session with customer_id
    Then the response status should be 200
    And the Stripe checkout call should use the locale "fr"
