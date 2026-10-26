Feature: Platform - Product Management
  Authenticated users can manage billing products within a SaaS app.

  Background:
    Given I am authenticated
    And a SaaS app "Product Test App" with slug "prod-test" exists

  Scenario: Create a product
    When I send a POST to "/platform/{saas_id}/products" with
      """
      {
        "name": "Pro Plan",
        "description": "Professional tier"
      }
      """
    Then the response status should be 201
    And the response JSON "name" should be "Pro Plan"
    And the response JSON should contain "id"
    And the response JSON should contain "stripe_product_id"
    And the response JSON "slug" should be "pro-plan"

  Scenario: List products (active only by default)
    Given a product "Active Product" exists for the SaaS app
    When I send a GET to "/platform/{saas_id}/products"
    Then the response status should be 200
    And the response JSON should be a non-empty list

  Scenario: Get a product by ID
    Given a product "Lookup Product" exists for the SaaS app
    When I send a GET to "/platform/{saas_id}/products/{product_id}"
    Then the response status should be 200
    And the response JSON "name" should be "Lookup Product"

  Scenario: Update a product
    Given a product "Old Product" exists for the SaaS app
    When I send a PATCH to "/platform/{saas_id}/products/{product_id}" with
      """
      {
        "name": "Renamed Product"
      }
      """
    Then the response status should be 200
    And the response JSON "name" should be "Renamed Product"

  Scenario: Get non-existent product returns 404
    When I send a GET to "/platform/{saas_id}/products/00000000-0000-0000-0000-000000000000"
    Then the response status should be 404

  Scenario: A product takes the slug of its metadata
    When I send a POST to "/platform/{saas_id}/products" with
      """
      {
        "name": "Team",
        "metadata": {"slug": "team", "limits": {"seats": 5}}
      }
      """
    Then the response status should be 201
    And the response JSON "slug" should be "team"

  Scenario: A plan slug cannot be used twice in a SaaS app
    Given a product "Pro Plan" exists for the SaaS app
    When I send a POST to "/platform/{saas_id}/products" with
      """
      {
        "name": "Another Pro",
        "slug": "pro-plan"
      }
      """
    Then the response status should be 409

  Scenario: Two SaaS apps can use the same plan slug
    Given a product "Pro Plan" exists for the SaaS app
    And a SaaS app "Other Product App" with slug "other-prod" exists
    When I send a POST to "/platform/{saas_id}/products" with
      """
      {
        "name": "Pro Plan"
      }
      """
    Then the response status should be 201
    And the response JSON "slug" should be "pro-plan"
