Feature: Usage Reporting
  Authenticated users can report metered usage events.

  Background:
    Given I am authenticated
    And a SaaS app "Usage App" with slug "usage-test" exists
    And a product "Usage Product" exists for the SaaS app
    And a metered price "Usage Price" exists for the product
    And a customer "usage_user" exists for the SaaS app
    And a subscription exists for the customer

  Scenario: Report a single usage event
    When I send a POST to "/usage/{saas_id}/report" with
      """
      {
        "subscription_id": "{subscription_id}",
        "quantity": 50,
        "action": "api_call"
      }
      """
    Then the response status should be 201
    And the response JSON should contain "id"
    And the response JSON "quantity" should be "50"

  Scenario: Report batch usage events
    When I report a batch of 3 usage events
    Then the response status should be 201
    And the response JSON should be a list of 3 items

  Scenario: Idempotency key prevents duplicates
    When I report usage with idempotency key "unique_key_001"
    Then the response status should be 201
    And I store the response "id" as "first_event_id"
    When I report usage with idempotency key "unique_key_001"
    Then the response status should be 201
    And the usage event should be the stored event "first_event_id"

  Scenario: The same idempotency key in a batch is recorded once
    When I report a batch of 2 usage events with the idempotency key "batch_key_001"
    Then the response status should be 201
    And the usage events of the batch should be the same event

  Scenario: Two SaaS apps can use the same idempotency key
    Given a second SaaS app "Second Usage App" with slug "usage-second" has a metered subscription
    When I report usage with idempotency key "shared_key_001"
    Then I store the response "id" as "first_event_id"
    When I report usage with idempotency key "shared_key_001" for the second SaaS app
    Then the response status should be 201
    And the usage event should not be the stored event "first_event_id"

  Scenario: A subscription of another SaaS app cannot receive usage
    Given a second SaaS app "Second Usage App" with slug "usage-second" has a metered subscription
    When I report usage on the second SaaS app for the first subscription
    Then the response status should be 404
