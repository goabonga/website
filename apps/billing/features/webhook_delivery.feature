Feature: Retried delivery of the SaaS notifications
  A notification is delivered by a Celery task. A failure that can succeed
  later (network error, 5xx, 429) is retried with a backoff, any other
  refusal is final, and every attempt sends the same event.

  Background:
    Given a SaaS app "Delivery App" with slug "delivery-app" exists
    And a product "Delivery Plan" exists for the SaaS app
    And a price "Delivery Price" exists for the product
    And a customer "wh_notif_user" exists for the SaaS app
    And a subscription exists for the customer
    And the SaaS app receives its notifications at "https://app.example.test/hooks" with the secret "shh"

  Scenario: A notification is delivered at the first attempt
    When I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_subscription_id}"
    Then the receiver should have been called 1 times

  Scenario: A server error is retried until the receiver accepts the event
    Given the receiver of the SaaS app answers with the statuses "503,502,200"
    When I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_subscription_id}"
    Then the response status should be 200
    And the receiver should have been called 3 times
    And every attempt should carry the same event identifier, body and signature

  Scenario: Throttling is retried
    Given the receiver of the SaaS app answers with the statuses "429,200"
    When I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_subscription_id}"
    Then the receiver should have been called 2 times

  Scenario: A refusal of the receiver is final
    Given the receiver of the SaaS app answers with the statuses "403,200"
    When I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_subscription_id}"
    Then the response status should be 200
    And the receiver should have been called 1 times

  Scenario: The delivery gives up after the configured number of attempts
    Given the notifications are tried at most 3 times
    And the receiver of the SaaS app answers with the statuses "500,500,500,500,500"
    When I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_subscription_id}"
    Then the response status should be 200
    And the receiver should have been called 3 times

  Scenario: A single attempt disables the retries
    Given the notifications are tried at most 1 times
    And the receiver of the SaaS app answers with the statuses "500,200"
    When I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_subscription_id}"
    Then the receiver should have been called 1 times

  Scenario: The notification is sent at once when the broker is unavailable
    Given the Celery broker is unavailable
    When I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_subscription_id}"
    Then the response status should be 200
    And the receiver should have been called 1 times
