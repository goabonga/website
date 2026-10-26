Feature: Background tasks
  Celery tasks report metered usage to Stripe, purge old usage events and
  push the product catalog to Stripe. Tasks run eagerly in the test process.

  Background:
    Given a SaaS application with slug "tasks-app" and a customer "tasks-user"

  Scenario: Pending usage events are reported to Stripe
    Given a subscription with a subscription item
    And a pending usage event of 7 units
    When I run the pending usage reporting task
    Then the task result should be processed 1, success 1, failed 0
    And the usage event should be "reported"

  Scenario: The usage report sent to Stripe uses a key scoped to the SaaS app
    Given a subscription with a subscription item
    And a pending usage event of 4 units with the idempotency key "order-1"
    When I run the pending usage reporting task
    Then Stripe should receive the idempotency key scoped to the SaaS app for "order-1"

  Scenario: Usage events without a subscription item fail
    Given a subscription without a subscription item
    And a pending usage event of 3 units
    When I run the pending usage reporting task
    Then the task result should be processed 1, success 0, failed 1
    And the usage event should be "failed"

  Scenario: Old reported usage events are deleted
    Given a subscription with a subscription item
    And a reported usage event of 2 units from 120 days ago
    When I run the usage cleanup task for events older than 90 days
    Then the cleanup task should delete 1 event

  Scenario: Products without a real Stripe identifier are pushed to Stripe
    Given a product "Imported" without a real Stripe identifier and a price of 1500 cents
    When I run the Stripe catalog sync task
    Then the sync task should report 1 product and 1 price synced

  Scenario: The beat schedule registers the periodic tasks
    Then the beat schedule should contain the tasks
      | task                                                          |
      | billing.tasks.usage_tasks.report_pending_usage                |
      | billing.tasks.usage_tasks.cleanup_old_usage_events            |
      | billing.tasks.stripe_sync_tasks.sync_all_products_to_stripe   |

  Scenario: The beat schedule follows the configured intervals
    Then the beat schedule should use the configured intervals
