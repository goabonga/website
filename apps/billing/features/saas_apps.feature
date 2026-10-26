Feature: Platform - SaaS App Management
  Authenticated users can manage SaaS applications.

  Background:
    Given I am authenticated

  Scenario: Create a SaaS app
    When I send a POST to "/platform/saas" with
      """
      {
        "name": "My SaaS App",
        "slug": "my-saas-app",
        "description": "A test SaaS application"
      }
      """
    Then the response status should be 201
    And the response JSON "name" should be "My SaaS App"
    And the response JSON "slug" should be "my-saas-app"
    And the response JSON "is_active" should be true
    And the response JSON should contain "id"

  Scenario: Create a SaaS app with duplicate slug returns 409
    Given a SaaS app "Existing App" with slug "duplicate-slug" exists
    When I send a POST to "/platform/saas" with
      """
      {
        "name": "Another App",
        "slug": "duplicate-slug"
      }
      """
    Then the response status should be 409

  Scenario: List SaaS apps
    Given a SaaS app "App One" with slug "app-one" exists
    Given a SaaS app "App Two" with slug "app-two" exists
    When I send a GET to "/platform/saas"
    Then the response status should be 200
    And the response JSON should be a list of 2 items

  Scenario: Get a SaaS app by ID
    Given a SaaS app "Lookup App" with slug "lookup-app" exists
    When I send a GET to "/platform/saas/{saas_id}"
    Then the response status should be 200
    And the response JSON "name" should be "Lookup App"

  Scenario: Update a SaaS app
    Given a SaaS app "Old Name" with slug "update-me" exists
    When I send a PATCH to "/platform/saas/{saas_id}" with
      """
      {
        "name": "New Name",
        "description": "Updated description"
      }
      """
    Then the response status should be 200
    And the response JSON "name" should be "New Name"

  Scenario: Get a non-existent SaaS app returns 404
    When I send a GET to "/platform/saas/00000000-0000-0000-0000-000000000000"
    Then the response status should be 404

  Scenario: Sync a SaaS app without products to Stripe
    Given a SaaS app "Empty App" with slug "sync-empty" exists
    When I send a POST to "/platform/saas/{saas_id}/sync-stripe"
    Then the response status should be 200
    And the response JSON "products_synced" should be "0"
    And the response JSON "prices_synced" should be "0"

  Scenario: A SaaS app stores its checkout URL allow-list
    When I send a POST to "/platform/saas" with
      """
      {
        "name": "Allow App",
        "slug": "allow-app",
        "checkout_url_allowlist": ["https://app.example.test/", "https://beta.example.test/billing"]
      }
      """
    Then the response status should be 201
    And the response JSON should contain "checkout_url_allowlist"
    And the checkout URL allow-list should be "https://app.example.test,https://beta.example.test/billing"

  Scenario: An invalid checkout URL allow-list entry is rejected
    When I send a POST to "/platform/saas" with
      """
      {
        "name": "Bad App",
        "slug": "bad-app",
        "checkout_url_allowlist": ["not-a-url"]
      }
      """
    Then the response status should be 422
