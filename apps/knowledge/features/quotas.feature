Feature: Usage quotas and API call tracking
  As the operator of a SaaS platform
  I want plans to limit resources and API calls to be counted per tenant
  So that usage can be bounded and billed

  Background:
    Given the plan limits are configured as follows
      | plan       | limit                       | value     |
      | free       | max_collections             | 3         |
      | free       | max_documents_per_collection| 100       |
      | free       | max_total_documents         | 200       |
      | free       | max_api_calls_per_month     | 1000      |
      | free       | max_storage_bytes           | 52428800  |
      | starter    | max_collections             | 10        |
      | pro        | max_total_documents         | 100000    |
      | enterprise | max_collections             | -1        |
      | enterprise | max_total_documents         | -1        |

  Scenario Outline: Plan limits
    Given the "<plan>" plan
    Then the plan limit "<limit>" should be <value>

    Examples:
      | plan       | limit                  | value   |
      | free       | max_collections        | 3       |
      | free       | max_total_documents    | 200     |
      | starter    | max_collections        | 10      |
      | pro        | max_total_documents    | 100000  |
      | enterprise | max_collections        | -1      |

  Scenario: A limit that is not configured is zero
    Given the "pro" plan
    Then the plan limit "max_collections" should be 0

  Scenario: A quota with room left is not exceeded
    Given a quota with limit 10 and 4 used
    Then the quota should not be exceeded
    And the quota should have 6 remaining
    And the quota should be 40 percent used

  Scenario: A quota close to its limit is flagged
    Given a quota with limit 10 and 9 used
    Then the quota should be near its limit
    And the quota should not be exceeded

  Scenario: A quota at its limit is exceeded
    Given a quota with limit 3 and 3 used
    Then the quota should be exceeded

  Scenario: An unlimited quota is never exceeded
    Given an unlimited quota with 5000 used
    Then the quota should not be exceeded
    And the quota should have -1 remaining

  Scenario: Creating a collection is refused when the plan limit is reached
    Given a user on the "free" plan owning 3 collections
    When the user tries to create a collection
    Then the creation should be refused with the quota "max_collections" at 3 of 3

  Scenario: Creating a collection is allowed below the plan limit
    Given a user on the "free" plan owning 2 collections
    When the user tries to create a collection
    Then the creation should be accepted

  Scenario: Enterprise organizations have no collection limit
    Given an organization on the "enterprise" plan owning 500 collections
    When the organization tries to create a collection
    Then the creation should be accepted

  Scenario: A successful API call is recorded for the tenant
    Given an API with call tracking
    When a client calls "/api/v1/ping" for tenant "cccccccc-cccc-cccc-cccc-cccccccccccc"
    Then the response status code should be 200
    And 1 API call should be recorded for tenant "cccccccc-cccc-cccc-cccc-cccccccccccc"

  Scenario: A failed API call is not recorded
    Given an API with call tracking
    When a client calls "/api/v1/missing" for tenant "cccccccc-cccc-cccc-cccc-cccccccccccc"
    Then the response status code should be 404
    And no API call should be recorded

  Scenario: Calls outside the API are not recorded
    Given an API with call tracking
    When a client calls "/health" for tenant "cccccccc-cccc-cccc-cccc-cccccccccccc"
    Then the response status code should be 200
    And no API call should be recorded

  Scenario: A tracking failure never fails the request
    Given an API with call tracking
    And the usage store is unavailable
    When a client calls "/api/v1/ping" for tenant "cccccccc-cccc-cccc-cccc-cccccccccccc"
    Then the response status code should be 200
