@browser
Feature: Plan slug and free-form limits of billing products in a browser
  As an administrator of the billing platform
  I want to name each plan and give it the limits its SaaS app reads
  So that every SaaS app can describe its own plans without the admin knowing them

  Scenario: The product form has no preset limit names
    Given a SaaS app exists with id "saas-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/new"
    Then "Plan Slug" should be visible
    And "+ Add Limit" should be visible
    And I should not see "max_collections"

  Scenario: A product is created with a slug and free-form limits
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/new"
    And I fill "Product Name" with "Pro"
    And I fill "Plan Slug" with "pro"
    And I click "+ Add Limit"
    And I fill "Limit name" with "seats"
    And I fill "Value" with "5"
    And I click "+ Add Limit"
    And I fill "css=.limit-row:nth-child(2) .limit-key" with "api_calls"
    And I fill "css=.limit-row:nth-child(2) .limit-value" with "1000"
    And I click "Create in Stripe"
    Then the URL should contain "/billing/saas/saas-1/products/prod-1?success="
    And the product should have been created with the slug "pro"
    And the product should have been created with the limits '{"seats": 5, "api_calls": 1000}'

  Scenario: Without a slug the billing service derives it from the name
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/new"
    And I fill "Product Name" with "Pro"
    And I click "Create in Stripe"
    Then the URL should contain "success="
    And the product should have been created without a slug

  Scenario: A slug with capitals or spaces is stopped by the form
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/new"
    And I fill "Product Name" with "Pro"
    And I fill "Plan Slug" with "Not A Slug"
    And I click "Create in Stripe"
    Then the URL should be "/billing/saas/saas-1/products/new"
    And no product should have been created

  Scenario: A limit with decimals is stopped by the form
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/new"
    And I fill "Product Name" with "Pro"
    And I click "+ Add Limit"
    And I fill "Limit name" with "seats"
    And I fill "css=.limit-value" with "2.5"
    And I click "Create in Stripe"
    Then the URL should be "/billing/saas/saas-1/products/new"
    And no product should have been created

  Scenario: A limit that is not written as a whole number is refused with an alert
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/new"
    And I fill "Product Name" with "Pro"
    And I click "+ Add Limit"
    And I fill "Limit name" with "seats"
    And I fill "css=.limit-value" with "1e3"
    And I click "Create in Stripe"
    Then the page should have alerted "must be a whole number"
    And the URL should be "/billing/saas/saas-1/products/new"
    And no product should have been created

  Scenario: A limit can be removed before the form is sent
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/new"
    And I fill "Product Name" with "Pro"
    And I click "+ Add Limit"
    And I fill "Limit name" with "seats"
    And I fill "Value" with "5"
    And I click "css=.remove-limit"
    And I click "Create in Stripe"
    Then the URL should contain "success="
    And the product should have been created with the limits '{}'

  Scenario: The edit form shows the slug and the limits of the product
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{"slug": "pro", "tier": "gold", "limits": {"seats": 5}}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/prod-1/edit"
    Then the field "Plan Slug" should contain "pro"
    And the field "css=.limit-key" should contain "seats"
    And the field "css=.limit-value" should contain "5"

  Scenario: Editing a product sends its new slug and limits
    Given the SaaS app "saas-1" has the product "pro" with the metadata '{"slug": "pro", "tier": "gold", "limits": {"old": 1}}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/prod-1/edit"
    And I fill "Plan Slug" with "business"
    And I fill "css=.limit-key" with "seats"
    And I fill "css=.limit-value" with "10"
    And I click "Save Changes"
    Then the URL should contain "/billing/saas/saas-1/products/prod-1?success="
    And the product should have been updated with the slug "business"
    And the product metadata should have been updated as '{"tier": "gold", "limits": {"seats": 10}}'

  Scenario: The product list shows the slug of each plan
    Given the SaaS app "saas-1" has the product "pro-plan" with the metadata '{}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products"
    Then I should see "pro-plan"

  Scenario: The product page shows its limits as they are
    Given the SaaS app "saas-1" has the product "pro-plan" with the metadata '{"limits": {"seats": 5000, "quota": -1}}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/prod-1"
    Then I should see "seats"
    And I should see "5,000"
    And I should not see "Unlimited"
