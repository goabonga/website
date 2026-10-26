@browser
Feature: Billing administration in a browser
  As an operator with the billing permissions
  I want to manage the SaaS apps, their products and prices, customers and subscriptions
  So that I can administrate the multi-SaaS billing platform

  Background:
    Given the billing SaaS apps list returns data
    And a SaaS app exists with id "saas-1"
    And the billing products list returns data for SaaS "saas-1"
    And a billing product exists with id "prod-1" for SaaS "saas-1"
    And the billing customers list returns data for SaaS "saas-1"
    And a billing customer exists with id "cust-1" for SaaS "saas-1"
    And the billing subscriptions list returns data for SaaS "saas-1"
    And a billing subscription exists with id "sub-1" for SaaS "saas-1"

  # --- Access and sidebar ---

  Scenario: The dashboard lists the SaaS apps
    Given I sign in with the scopes "billing:read"
    When I navigate to "/billing"
    Then the page title should be "Billing Dashboard - Internal Admin"
    And I should see "SaaS Applications (1)"
    And I should see "Test App"
    And I should see "test-app"
    And the sidebar menu should highlight only "Billing"
    And the browser should report no errors

  Scenario: Only the holders of the billing scope see the Billing link
    Given the analytics overview returns data
    And I sign in with the scopes "analytics:*"
    When I navigate to "/analytics"
    Then the sidebar menu should not have a link "Billing"

  Scenario: The Billing link leads to the dashboard
    Given the analytics overview returns data
    And I sign in with the scopes "analytics:* billing:read"
    When I navigate to "/analytics"
    Then the sidebar menu should have a link "Billing" to "/billing"
    When I follow the sidebar link "Billing"
    Then the URL should be "/billing"
    And I should see "Test App"

  Scenario: A user without the billing scope gets the access denied page
    Given I sign in with the scopes "contacts:read"
    When I navigate to "/billing"
    Then the page title should contain "Access Denied"
    And I should see "billing:read"

  Scenario: A user who may only read cannot create a SaaS app
    Given I sign in with the scopes "billing:read"
    When I navigate to "/billing/saas/new"
    Then the page title should contain "Access Denied"
    And I should see "billing:write"

  Scenario: An anonymous visitor comes back to the page asked for after the login
    Given a user holding the scopes "billing:*" exists at the provider
    When I navigate to "/billing/saas/saas-1/subscriptions?status=active"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/billing/saas/saas-1/subscriptions?status=active"
    And I should see "stripe_sub_123"

  # --- SaaS apps ---

  Scenario: A SaaS app is created from the form
    Given creating a SaaS app succeeds
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing"
    And I click "+ New SaaS App"
    Then the URL should be "/billing/saas/new"
    When I fill "Name" with "My SaaS"
    And I fill "Slug" with "my-saas"
    And I fill "Description" with "A test SaaS app"
    And I click "Create SaaS App"
    Then the URL should contain "/billing/saas/saas-new?success="
    And I should see "SaaS app created successfully"
    And the billing service should have been asked to create the SaaS app "My SaaS"

  Scenario: A SaaS app the billing service refuses is reported on the form
    Given creating a SaaS app fails
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/new"
    And I fill "Name" with "Bad App"
    And I fill "Slug" with "bad-app"
    And I click "Create SaaS App"
    Then the URL should contain "/billing/saas/new?error="
    And I should see "Failed to create SaaS app"

  Scenario: The form requires a name and a slug
    Given I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/new"
    And I click "Create SaaS App"
    Then the URL should be "/billing/saas/new"
    And the billing service should not have been asked to create a SaaS app

  Scenario: The detail of a SaaS app links to its products, customers and subscriptions
    Given I sign in with the scopes "billing:*"
    When I navigate to "/billing"
    And I click "Test App"
    Then the URL should be "/billing/saas/saas-1"
    And I should see "Recent Customers"
    And I should see "customer@example.com"
    And the sidebar menu should highlight only "Billing"
    When I click "+ New Product" in the page content
    Then the URL should be "/billing/saas/saas-1/products/new"

  Scenario: A SaaS app that does not exist sends the user back to the dashboard
    Given a SaaS app does not exist
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/unknown"
    Then the URL should contain "/billing?error="
    And I should see "SaaS app not found"

  Scenario: A SaaS app is updated from its edit form
    Given updating a SaaS app succeeds
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1"
    And I click "Edit" in the page content
    Then the URL should be "/billing/saas/saas-1/edit"
    When I fill "Name" with "Renamed SaaS"
    And I click "Update SaaS App"
    Then the URL should contain "/billing/saas/saas-1?success="
    And I should see "SaaS app updated successfully"

  Scenario: Unticking Active deactivates the SaaS app
    Given updating a SaaS app succeeds
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/edit"
    And I click "css=input[name=is_active]"
    And I click "Update SaaS App"
    Then the SaaS app should have been updated as inactive

  Scenario: A failed update is reported on the form
    Given updating a SaaS app fails
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/edit"
    And I click "Update SaaS App"
    Then I should see "Failed to update SaaS app"

  # --- Products and prices ---

  Scenario: The products of a SaaS app are listed
    Given I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products"
    Then I should see "Test Product"
    And I should see "stripe_prod_123"
    And the sidebar menu should highlight only "Billing"
    When I click "Test Product"
    Then the URL should be "/billing/saas/saas-1/products/prod-1"
    And I should see "Feature 1"

  Scenario: A product is created with a feature
    Given creating a billing product succeeds for SaaS "saas-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products"
    And I click "+ New Product"
    Then the URL should be "/billing/saas/saas-1/products/new"
    When I fill "Product Name" with "Pro"
    And I click "+ Add Feature"
    And I fill "Feature description" with "Unlimited projects"
    And I click "Create in Stripe"
    Then the URL should contain "/billing/saas/saas-1/products/prod-new?success="
    And I should see "Product created in Stripe"
    And the billing service should have been asked to create the product "Pro"
    And the created product should list the feature "Unlimited projects"

  Scenario: A product the billing service refuses is reported on the form
    Given creating a billing product fails for SaaS "saas-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/new"
    And I fill "Product Name" with "Pro"
    And I click "Create in Stripe"
    Then I should see "Failed to create product"

  Scenario: A product is updated from its edit form
    Given updating a billing product succeeds for SaaS "saas-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/prod-1"
    And I click "Edit Product"
    Then the URL should be "/billing/saas/saas-1/products/prod-1/edit"
    When I fill "Product Name" with "Pro plus"
    And I click "Save Changes"
    Then the URL should contain "/billing/saas/saas-1/products/prod-1?success="
    And I should see "Product updated"

  Scenario: A product that does not exist sends the user back to the list
    Given a billing product does not exist for SaaS "saas-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/unknown"
    Then the URL should contain "/billing/saas/saas-1/products?error="
    And I should see "Product not found"

  Scenario: A price is created for a product
    Given creating a billing price succeeds for SaaS "saas-1" product "prod-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/prod-1"
    And I click "+ New Price"
    Then the URL should be "/billing/saas/saas-1/products/prod-1/prices/new"
    When I fill "Amount (in cents) *" with "1999"
    And I click "Create in Stripe"
    Then the URL should contain "/billing/saas/saas-1/products/prod-1?success="
    And I should see "Price created"

  Scenario: A price the billing service refuses is reported
    Given creating a billing price fails for SaaS "saas-1" product "prod-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/prod-1/prices/new"
    And I fill "Amount (in cents) *" with "1999"
    And I click "Create in Stripe"
    Then I should see "Failed to create price"

  Scenario: A price is toggled from the product page
    Given toggling a billing price succeeds for SaaS "saas-1" product "prod-1" price "price-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/products/prod-1"
    And I click "Deactivate"
    Then the URL should contain "/billing/saas/saas-1/products/prod-1?success="

  # --- Customers ---

  Scenario: The customers of a SaaS app are listed with their detail
    Given I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/customers"
    Then I should see "customer@example.com"
    And I should see "ext-cust-001"
    When I click "View"
    Then the URL should be "/billing/saas/saas-1/customers/cust-1"
    And I should see "Customer Details"
    And I should see "stripe_cus_123"

  Scenario: The next page of customers is offered when a page is full
    Given the billing lists show 5 rows per page
    And the billing customers list returns 5 customers for SaaS "saas-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/customers"
    Then I should see "Page 1"
    When I click "Next →"
    Then the URL should be "/billing/saas/saas-1/customers?page=2"
    And I should see "Page 2"
    And I should see "← Previous"

  Scenario: There is no next page when the last page is not full
    Given the billing lists show 5 rows per page
    And the billing customers list returns 4 customers for SaaS "saas-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/customers"
    Then I should see "Page 1"
    And "Next →" should be hidden

  Scenario: A customer that does not exist sends the user back to the list
    Given a billing customer does not exist for SaaS "saas-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/customers/unknown"
    Then the URL should contain "/billing/saas/saas-1/customers?error="
    And I should see "Customer not found"

  Scenario: The Stripe portal of a customer is opened
    Given the SaaS app "saas-1" accepts the return URL "https://app.example.test/account"
    And a billing customer portal URL exists for SaaS "saas-1" customer "cust-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/customers/cust-1"
    And I click "Open Stripe Portal"
    Then I should see "External site"
    And I should see "https://billing.stripe.com/portal/session_123"
    And the billing portal should have been requested with the return URL "https://app.example.test/account"

  Scenario: The portal needs a return URL the SaaS app accepts
    Given the SaaS app "saas-1" has no checkout URL allow-list
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/customers/cust-1"
    And I click "Open Stripe Portal"
    Then the URL should contain "/billing/saas/saas-1/customers/cust-1?error="
    And I should see "No return URL"
    And no billing portal should have been requested

  Scenario: A portal the billing service cannot open is reported
    Given the SaaS app "saas-1" accepts the return URL "https://app.example.test/account"
    And a billing customer portal fails for SaaS "saas-1" customer "cust-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/customers/cust-1"
    And I click "Open Stripe Portal"
    Then the URL should contain "/billing/saas/saas-1/customers/cust-1?error="
    And I should see "Failed to create portal session"

  # --- Subscriptions ---

  Scenario: The subscriptions are listed and filtered by status
    Given I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/subscriptions"
    Then I should see "stripe_sub_123"
    When I select "Canceled" from "status"
    And I click "Filter"
    Then the URL should contain "status=canceled"

  Scenario: The detail of a subscription shows its customer
    Given I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/subscriptions"
    And I click "View"
    Then the URL should be "/billing/saas/saas-1/subscriptions/sub-1"
    And I should see "Subscription Info"
    And I should see "customer@example.com"
    And the sidebar menu should highlight only "Billing"

  Scenario: A subscription that does not exist sends the user back to the list
    Given a billing subscription does not exist for SaaS "saas-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/subscriptions/unknown"
    Then the URL should contain "/billing/saas/saas-1/subscriptions?error="
    And I should see "Subscription not found"

  Scenario: A subscription is canceled at the end of the period
    Given canceling a billing subscription succeeds for SaaS "saas-1" subscription "sub-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/subscriptions/sub-1"
    And I click "Cancel Subscription"
    And I click "Confirm Cancellation"
    Then the URL should contain "/billing/saas/saas-1/subscriptions/sub-1?success="
    And I should see "Subscription scheduled for cancellation"

  Scenario: A subscription that cannot be canceled is reported
    Given canceling a billing subscription fails for SaaS "saas-1" subscription "sub-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/subscriptions/sub-1"
    And I click "Cancel Subscription"
    And I click "Confirm Cancellation"
    Then I should see "Failed to cancel subscription"

  Scenario: A subscription is synchronized from Stripe
    Given syncing a billing subscription succeeds for SaaS "saas-1" subscription "sub-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/subscriptions/sub-1"
    And I click "Sync from Stripe"
    Then the URL should contain "/billing/saas/saas-1/subscriptions/sub-1?success="
    And I should see "Subscription synced from Stripe"

  Scenario: A subscription that cannot be synchronized is reported
    Given syncing a billing subscription fails for SaaS "saas-1" subscription "sub-1"
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/subscriptions/sub-1"
    And I click "Sync from Stripe"
    Then I should see "Failed to sync subscription"
