Feature: Plan slug and free-form limits of billing products
  As an administrator of the billing platform
  I want to name each plan and give it the limits its SaaS app reads
  So that every SaaS app can describe its own plans without the admin knowing them

  Background:
    Given I am a super admin

  @billing-plans
  Scenario: The product form has no preset limit names
    Given a SaaS app exists with id "saas-1"
    When I send a GET request to "/billing/saas/saas-1/products/new"
    Then the response status code should be 200
    And the response should contain "Add Limit"
    And the response should not contain "max_collections"
    And the response should not contain "limit-presets"

  @billing-plans
  Scenario: The product form checks the shape of the slug
    Given a SaaS app exists with id "saas-1"
    When I send a GET request to "/billing/saas/saas-1/products/new"
    Then the response status code should be 200
    And the response should contain "[a-z0-9]+(-[a-z0-9]+)*"

  @billing-plans
  Scenario: The slug is sent as its own field
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{}'
    When I send a POST request to "/billing/saas/saas-1/products/new" with form data
      | field       | value |
      | name        | Pro   |
      | slug        | pro   |
      | limits_json | {"seats": 5, "api_calls": 1000} |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success="
    And the product should have been created with the slug "pro"

  @billing-plans
  Scenario: Without a slug the billing service derives it from the name
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{}'
    When I send a POST request to "/billing/saas/saas-1/products/new" with form data
      | field | value |
      | name  | Pro   |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success="
    And the product should have been created without a slug

  @billing-plans
  Scenario: A slug with capitals or spaces is refused
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{}'
    When I send a POST request to "/billing/saas/saas-1/products/new" with form data
      | field | value       |
      | name  | Pro         |
      | slug  | Not A Slug  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/billing/saas/saas-1/products/new?error="
    And no product should have been created

  @billing-plans
  Scenario: A limit that is not a whole number is refused
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{}'
    When I send a POST request to "/billing/saas/saas-1/products/new" with form data
      | field       | value           |
      | name        | Pro             |
      | limits_json | {"seats": 2.5}  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "must+be+a+whole+number"
    And no product should have been created

  @billing-plans
  Scenario: Editing a product sends its new slug and keeps the metadata the form does not know
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{"slug": "pro", "tier": "gold", "limits": {"old": 1}}'
    When I send a POST request to "/billing/saas/saas-1/products/prod-1/edit" with form data
      | field       | value          |
      | name        | Pro            |
      | slug        | business       |
      | is_active   | true           |
      | limits_json | {"seats": 10}  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success="
    And the product should have been updated with the slug "business"
    And the product metadata should have been updated as '{"tier": "gold", "limits": {"seats": 10}}'

  @billing-plans
  Scenario: A limit without a name is refused when editing
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{}'
    When I send a POST request to "/billing/saas/saas-1/products/prod-1/edit" with form data
      | field       | value    |
      | name        | Pro      |
      | limits_json | {" ": 1} |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/products/prod-1/edit?error="
    And no product should have been updated

  @billing-plans
  Scenario: The product list shows the slug of each plan
    Given the SaaS app "saas-1" has the product "pro-plan" with the metadata '{}'
    When I send a GET request to "/billing/saas/saas-1/products"
    Then the response status code should be 200
    And the response should contain "pro-plan"

  @billing-plans
  Scenario: The product page shows its limits as they are
    Given the SaaS app "saas-1" has the product "pro-plan" with the metadata '{"limits": {"seats": 5000, "quota": -1}}'
    When I send a GET request to "/billing/saas/saas-1/products/prod-1"
    Then the response status code should be 200
    And the response should contain "seats"
    And the response should contain "5,000"
    And the response should not contain "Unlimited"
