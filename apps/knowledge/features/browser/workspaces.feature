@browser
Feature: Workspace switching, plan upgrade and settings pages in a browser
  As a member of one or more workspaces
  I want to switch workspace, upgrade the plan and change the settings
  So that I can run my workspaces from the web application

  Scenario: A member of two workspaces switches from the sidebar
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And "Alice" owns the workspace "Beta" on the "pro" plan
    And I have signed in as "Alice" through the identity provider
    When I select "Beta" from "tenant_id"
    Then the URL should be "/dashboard"
    And the workspace switcher should show "Beta"
    And the dashboard should show the plan "Pro"
    When I navigate to "/collections"
    Then the workspace switcher should show "Beta"
    When I select "Acme" from "tenant_id"
    Then the workspace switcher should show "Acme"
    And the dashboard should show the plan "Free"

  Scenario: A single workspace is shown without a switcher
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And I have signed in as "Alice" through the identity provider
    Then I should see "Acme"
    And "css=select[name=tenant_id]" should be hidden

  Scenario: The billing page lists the plans and marks the current one
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And the billing service offers the plan "Free" at 0 cents a month or 0 cents a year
    And the billing service offers the plan "Pro" at 2900 cents a month or 29000 cents a year
    And I have signed in as "Alice" through the identity provider
    When I click "Billing"
    Then the URL should be "/tenants/pricing"
    And the sidebar item "Billing" should be the active one
    And I should see "Choose Your Plan"
    And I should see "Current Plan"
    And I should see "Upgrade to Pro"

  Scenario: A workspace without subscription is sent to the payment page
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And the billing service offers the plan "Free" at 0 cents a month or 0 cents a year
    And the billing service offers the plan "Pro" at 2900 cents a month or 29000 cents a year
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/pricing"
    And I click "Upgrade to Pro"
    Then I should see "You're subscribing to"
    When I click "Continue to Payment"
    Then I should see "Payment successful"
    And the billing service created a checkout for the workspace "Acme" and the price "Pro-month"

  Scenario: A subscriber previews and confirms an upgrade
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "starter" plan
    And the billing service offers the plan "Starter" at 900 cents a month or 9000 cents a year
    And the billing service offers the plan "Pro" at 2900 cents a month or 29000 cents a year
    And the billing service holds the subscription "sub_1" of the workspace
    And the billing service quotes 1500 cents for the upgrade after a credit of 500 cents
    And the billing service accepts the upgrades
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/pricing"
    And I click "Upgrade to Pro"
    Then I should see "Confirm Plan Upgrade"
    And I should see "Amount due today"
    And I should see "$15"
    When I click "Confirm Upgrade"
    Then I should see "Plan upgraded successfully"
    And the subscription "sub_1" was upgraded to the price "Pro-month"

  Scenario: The upgrade can be cancelled from the confirmation
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "starter" plan
    And the billing service offers the plan "Starter" at 900 cents a month or 9000 cents a year
    And the billing service offers the plan "Pro" at 2900 cents a month or 29000 cents a year
    And the billing service holds the subscription "sub_1" of the workspace
    And the billing service quotes 1500 cents for the upgrade after a credit of 500 cents
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/pricing"
    And I click "Upgrade to Pro"
    And I click "Cancel"
    Then "Confirm Plan Upgrade" should be hidden
    And the billing service made no upgrade

  Scenario: A billing outage is reported on the billing page
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And the billing service refuses every request
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/pricing"
    Then I should see "Unable to load pricing"

  Scenario: An administrator renames the workspace
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And I have signed in as "Alice" through the identity provider
    When I click "General"
    Then the URL should be "/tenants/settings"
    And I should see "Usage & Quotas"
    And the sidebar item "General" should be the active one
    When I fill "Workspace Name" with "Acme Corp"
    And I click "Save Changes"
    Then I should see "Acme Corp"
    And the workspace "Acme Corp" should exist on the "free" plan
    And the sidebar item "General" should be the active one

  Scenario: The settings show the plan and lead to the billing page
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/settings"
    And I click "Upgrade"
    Then the URL should be "/tenants/pricing"

  Scenario: A regular member does not see the workspace administration
    Given a user "Bob" who holds every knowledge scope
    And "Bob" is a member of the workspace "Acme" on the "free" plan
    And I have signed in as "Bob" through the identity provider
    Then the navigation should not contain a link "General"
    And the navigation should not contain a link "Members"
    When I navigate to "/tenants/settings"
    Then the page title should be "Access Denied - Knowledge API"
    And I should see "You don't have permission to access this resource."
    When I click "Go to Dashboard"
    Then the URL should be "/dashboard"

  Scenario: The workspace pages only lead to pages that exist
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And "Alice" owns the workspace "Beta" on the "pro" plan
    And the billing service offers the plan "Free" at 0 cents a month or 0 cents a year
    And the billing service offers the plan "Pro" at 2900 cents a month or 29000 cents a year
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/dashboard"
    Then every link of the page leads to a page of the application
    When I click "Manage"
    Then the URL should be "/tenants/settings"
    And every link of the page leads to a page of the application
    When I navigate to "/tenants/pricing"
    Then every link of the page leads to a page of the application
