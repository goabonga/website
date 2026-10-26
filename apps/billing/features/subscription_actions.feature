Feature: Platform - Subscription cancel and reactivate actions
  A tenant cancels a subscription at the end of the paid period (the default)
  or immediately, and can undo a scheduled cancellation.

  Background:
    Given I am authenticated
    And a SaaS app "Action App" with slug "action-app" exists
    And a product "Action Product" exists for the SaaS app
    And a price "Action Price" exists for the product
    And a customer "action_user" exists for the SaaS app
    And a subscription exists for the customer
    And Stripe runs subscriptions until the end of the paid period

  Scenario: Cancel at the end of the period by default
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/cancel"
    Then the response status should be 200
    And the response JSON "status" should be "active"
    And the response JSON "cancel_at_period_end" should be true

  Scenario: Cancel at the end of the period explicitly
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/cancel" with
      """
      {"cancel_at_period_end": true}
      """
    Then the response status should be 200
    And the response JSON "cancel_at_period_end" should be true

  Scenario: Cancel immediately
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/cancel" with
      """
      {"cancel_at_period_end": false}
      """
    Then the response status should be 200
    And the response JSON "status" should be "canceled"
    And the response JSON should contain "canceled_at"

  Scenario: Reactivate a subscription scheduled for cancellation
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/cancel"
    And I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/reactivate"
    Then the response status should be 200
    And the response JSON "status" should be "active"
    And the response JSON "cancel_at_period_end" should be false

  Scenario: Reactivating a running subscription changes nothing
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/reactivate"
    Then the response status should be 200
    And the response JSON "cancel_at_period_end" should be false

  Scenario: A canceled subscription cannot be reactivated
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/cancel" with
      """
      {"cancel_at_period_end": false}
      """
    And I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/reactivate"
    Then the response status should be 409

  Scenario: A canceled subscription cannot be canceled again
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/cancel" with
      """
      {"cancel_at_period_end": false}
      """
    And I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/cancel"
    Then the response status should be 409

  Scenario: A subscription of another SaaS app is not found
    Given a SaaS app "Other Action App" with slug "other-action-app" exists
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/cancel"
    Then the response status should be 404

  Scenario: The actions require authentication
    Given I am not authenticated
    When I send a POST to "/platform/{saas_id}/subscriptions/{subscription_id}/cancel"
    Then the response status should be 401
