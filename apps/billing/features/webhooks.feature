Feature: Stripe Webhooks
  Stripe sends webhook events that update the billing database. The signature
  of the payload is the authentication: Stripe cannot send a bearer token.

  Scenario: Customer created webhook
    Given a SaaS app "Webhook App" with slug "webhook-test" exists
    When I receive a Stripe "customer.created" event with customer "cus_webhook_test" for SaaS "{saas_id}"
    Then the response status should be 200

  Scenario: Customer deleted webhook
    Given a SaaS app "Webhook App" with slug "webhook-del" exists
    And a customer "wh_del_user" exists for the SaaS app
    When I receive a Stripe "customer.deleted" event for customer "{stripe_customer_id}"
    Then the response status should be 200

  Scenario: Checkout session completed webhook creates subscription
    Given a SaaS app "Webhook App" with slug "webhook-checkout" exists
    And a customer "wh_checkout_user" exists for the SaaS app
    When I receive a Stripe "checkout.session.completed" event
    Then the response status should be 200

  Scenario: Invoice paid webhook
    Given a SaaS app "Webhook App" with slug "webhook-inv" exists
    And a product "Webhook Product" exists for the SaaS app
    And a price "Webhook Price" exists for the product
    And a customer "wh_inv_user" exists for the SaaS app
    And a subscription exists for the customer
    When I receive a Stripe "invoice.paid" event for subscription "{stripe_subscription_id}"
    Then the response status should be 200

  Scenario: Subscription updated webhook
    Given a SaaS app "Webhook App" with slug "webhook-sub-upd" exists
    And a product "Webhook Product" exists for the SaaS app
    And a price "Webhook Price" exists for the product
    And a customer "wh_sub_user" exists for the SaaS app
    And a subscription exists for the customer
    When I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_subscription_id}"
    Then the response status should be 200

  Scenario: Invalid webhook signature returns 400
    When I receive a Stripe event with invalid signature
    Then the response status should be 400

  Scenario: A webhook without bearer token is processed when it is signed
    Given a SaaS app "Webhook App" with slug "webhook-anon" exists
    When I receive a Stripe "customer.created" event with customer "cus_webhook_anon" for SaaS "{saas_id}"
    Then the response status should be 200

  Scenario: A webhook sent through the proxy with its token is processed
    Given the webhooks proxy sends its bearer token
    And a SaaS app "Webhook App" with slug "webhook-proxy" exists
    When I receive a Stripe "customer.created" event with customer "cus_webhook_proxy" for SaaS "{saas_id}"
    Then the response status should be 200

  Scenario: The signature is still required when a token is sent
    Given the webhooks proxy sends its bearer token
    When I receive a Stripe event with invalid signature
    Then the response status should be 400

  Scenario: A bearer token is required when the deployment asks for one
    Given Stripe webhooks require the scope "billing:webhooks"
    And a SaaS app "Webhook App" with slug "webhook-scope" exists
    When I receive a Stripe "customer.created" event with customer "cus_webhook_scope" for SaaS "{saas_id}"
    Then the response status should be 401

  Scenario: A bearer token with the required scope is accepted
    Given Stripe webhooks require the scope "billing:webhooks"
    And the webhooks proxy sends its bearer token
    And a SaaS app "Webhook App" with slug "webhook-scope-ok" exists
    When I receive a Stripe "customer.created" event with customer "cus_webhook_scope_ok" for SaaS "{saas_id}"
    Then the response status should be 200

  Scenario: A completed checkout stores its session on the subscription
    Given a SaaS app "Webhook App" with slug "webhook-session" exists
    And a customer "wh_session_user" exists for the SaaS app
    When I receive a Stripe "checkout.session.completed" event
    Then the response status should be 200
    And the SaaS app has a subscription created from the checkout session "cs_bdd_webhook"

  Scenario: A checkout session of another SaaS app is ignored
    Given a SaaS app "Webhook App" with slug "webhook-first" exists
    And a customer "wh_first_user" exists for the SaaS app
    And another SaaS app "Other Webhook App" with slug "webhook-second" exists
    When I receive a Stripe "checkout.session.completed" event
    Then the response status should be 200
    And the first SaaS app has no subscription

  Scenario: A customer created for an unknown SaaS app is ignored
    When I receive a Stripe "customer.created" event with customer "cus_webhook_ghost" for SaaS "00000000-0000-0000-0000-000000000000"
    Then the response status should be 200

  Scenario: The SaaS app is notified with its slug, plan slug, price, limits and an event id
    Given a SaaS app "Webhook App" with slug "webhook-notified" exists
    And a product "Notified Plan" exists for the SaaS app
    And a price "Notified Price" exists for the product
    And the plan "gold" of the SaaS app has the limits '{"max_seats": 7, "emails_per_day": -1}'
    And a customer "wh_notif_user" exists for the SaaS app
    And a subscription exists for the customer
    And the SaaS app receives its notifications at "https://app.example.test/hooks" with the secret "shh"
    When I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_subscription_id}"
    Then the response status should be 200
    And the SaaS app should receive one notification
    And the notification should be a "subscription.updated" of the SaaS app "webhook-notified"
    And the notification should carry the plan "gold" with the limits '{"max_seats": 7, "emails_per_day": -1}'
    And the notification should be signed with the secret of the SaaS app

  Scenario: A Stripe event delivered twice produces notifications with the same identifier
    Given a SaaS app "Webhook App" with slug "webhook-twice" exists
    And a product "Twice Plan" exists for the SaaS app
    And a price "Twice Price" exists for the product
    And a customer "wh_notif_user" exists for the SaaS app
    And a subscription exists for the customer
    And the SaaS app receives its notifications at "https://app.example.test/hooks" with the secret "shh"
    And the Stripe event identifier is "evt_delivered_twice"
    When I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_subscription_id}"
    And I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_subscription_id}"
    Then both notifications should have the same identifier
