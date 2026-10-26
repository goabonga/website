Feature: Data model
  Billing data is stored in SQLAlchemy models: SaaS applications own
  products, prices and customers; customers own subscriptions; subscriptions
  own usage events.

  Scenario: A SaaS application gets default values
    Given a stored SaaS application "Model App" with slug "model-app"
    When I reload the SaaS application "model-app"
    Then the SaaS application is active
    And the SaaS application has an identifier and a creation date

  Scenario: SaaS application slugs are unique
    Given a stored SaaS application "First" with slug "taken-slug"
    When I try to store another SaaS application "Second" with slug "taken-slug"
    Then the database rejects it as a duplicate

  Scenario: A product holds prices with sensible defaults
    Given a stored SaaS application "Model App" with slug "catalog-app"
    And a stored product "Pro" with a price for the SaaS application
    When I reload the price
    Then the price is a recurring licensed price in "usd"

  Scenario: A customer can be soft deleted
    Given a stored SaaS application "Model App" with slug "customer-app"
    And a stored customer "user-1" for the SaaS application
    When I soft delete the customer
    Then the customer is flagged as deleted

  Scenario: Subscriptions start active and usage events start pending
    Given a stored SaaS application "Model App" with slug "usage-app"
    And a stored customer "user-2" for the SaaS application
    And a stored subscription for the customer
    When I store a usage event of 5 units for the subscription
    Then the subscription status is "active"
    And the usage event status is "pending"

  Scenario: Two SaaS applications can reuse a plan slug
    Given a tenant "Alpha" with slug "alpha" and customer "a-1"
    And a tenant "Beta" with slug "beta" and customer "b-1"
    When I store a product with plan slug "pro" for "alpha"
    And I store a product with plan slug "pro" for "beta"
    Then the database accepts it

  Scenario: A plan slug is unique inside a SaaS application
    Given a tenant "Alpha" with slug "alpha" and customer "a-1"
    When I store a product with plan slug "pro" for "alpha"
    And I store a product with plan slug "pro" for "alpha"
    Then the database rejects it as a duplicate

  Scenario: Two SaaS applications can reuse an idempotency key
    Given a tenant "Alpha" with slug "alpha" and customer "a-1"
    And a tenant "Beta" with slug "beta" and customer "b-1"
    When I store a usage event with idempotency key "evt-1" for "alpha"
    And I store a usage event with idempotency key "evt-1" for "beta"
    Then the database accepts it

  Scenario: An idempotency key is unique inside a SaaS application
    Given a tenant "Alpha" with slug "alpha" and customer "a-1"
    When I store a usage event with idempotency key "evt-1" for "alpha"
    And I store a usage event with idempotency key "evt-1" for "alpha"
    Then the database rejects it as a duplicate
