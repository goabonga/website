Feature: Plan limits from billing
  As the operator of a SaaS platform
  I want the quotas to follow the plans I edit in the billing service
  So that changing a plan changes what customers may do, without a deployment

  Background:
    Given the fail-safe limits are configured as follows
      | plan | limit           | value |
      | pro  | max_collections | 5     |
      | *    | max_collections | 1     |
    And the billing service defines the plan "pro" with the limits
      | limit           | value |
      | max_collections | 50    |
      | max_seats       | -1    |

  Scenario: The limits of the plan are the ones of billing
    When the application asks for the limit "max_collections" of the "pro" plan
    Then the limit should be 50
    And billing should have been asked once

  Scenario: Limits are named by the application and can be unlimited
    When the application asks for the limit "max_seats" of the "pro" plan
    Then the limit should be -1

  Scenario: A limit billing does not define is zero
    When the application asks for the limit "max_storage_bytes" of the "pro" plan
    Then the limit should be 0

  Scenario: Creating a collection is refused with the limit of billing
    Given an organization on the "pro" plan owning 50 collections
    When the organization tries to create a collection
    Then the creation should be refused with the quota "max_collections" at 50 of 50

  Scenario: Billing being down, the fail-safe limits apply
    Given the billing service cannot be reached
    When the application asks for the limit "max_collections" of the "pro" plan
    Then the limit should be 5

  Scenario: A plan the fail-safe does not list uses the wildcard entry
    Given the billing service cannot be reached
    When the application asks for the limit "max_collections" of the "starter" plan
    Then the limit should be 1

  Scenario: An outage does not make every check wait for billing
    Given the billing service cannot be reached
    When the application asks for the limit "max_collections" of the "pro" plan
    And the application asks for the limit "max_collections" of the "pro" plan
    Then billing should have been asked once

  Scenario: Billing is asked again after the outage
    Given the billing service cannot be reached
    When the application asks for the limit "max_collections" of the "pro" plan
    And billing recovers and the back-off is over
    And the application asks for the limit "max_collections" of the "pro" plan
    Then the limit should be 50

  Scenario: Billing without the plan applies the fail-safe
    When the application asks for the limit "max_collections" of the "starter" plan
    Then the limit should be 1

  Scenario: Without billing configuration the fail-safe applies
    Given the billing service is not configured
    When the application asks for the limit "max_collections" of the "pro" plan
    Then the limit should be 5
