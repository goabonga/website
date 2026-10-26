Feature: Workspace switching, plan upgrade and settings
  As a member of one or several workspaces
  I want to switch between them, manage their plan and their settings
  So that each team works in its own space

  Background:
    Given the workspace database is in memory
    And the billing client is in memory

  Scenario: Switching workspace sets the active workspace
    Given I am the owner of the workspace "Acme" on the "free" plan
    And I also belong to the workspace "Globex"
    When I switch to the workspace "Globex"
    Then the response status code should be 302
    And I should be redirected to "/dashboard"
    And the browser should receive the cookies "active_tenant_id"
    And the active workspace cookie should designate "Globex"

  Scenario: Switching to a workspace I do not belong to is ignored
    Given I am the owner of the workspace "Acme" on the "free" plan
    And a workspace "Secret" exists that I do not belong to
    When I switch to the workspace "Secret"
    Then the response status code should be 302
    And the browser should not receive the cookie "active_tenant_id"

  Scenario: The pricing page compares the plans of the billing service
    Given I am the owner of the workspace "Acme" on the "free" plan
    And the billing client lists the plans "Starter" at 900 cents and "Pro" at 2900 cents per month
    When I open "/organizations/pricing"
    Then the response status code should be 200
    And the page should say "Starter"
    And the page should say "Pro"

  Scenario: The pricing page needs a workspace
    Given I am signed in without a workspace
    When I open "/organizations/pricing"
    Then the response status code should be 302
    And I should be redirected to "/dashboard"

  Scenario: The pricing page reports a billing failure
    Given I am the owner of the workspace "Acme" on the "free" plan
    And the billing client is failing
    When I open "/organizations/pricing"
    Then the response status code should be 200
    And the page should say "Unable to load pricing"

  Scenario: Choosing a plan redirects to the payment page
    Given I am the owner of the workspace "Acme" on the "free" plan
    When I choose the price "price_pro_month"
    Then the response status code should be 303
    And I should be redirected to "https://checkout.example.test/session"
    And the billing service should have created a checkout for the workspace "Acme" and the price "price_pro_month"

  Scenario: Choosing a plan without billing configured goes back to pricing
    Given I am the owner of the workspace "Acme" on the "free" plan
    And billing is not configured
    When I choose the price "price_pro_month"
    Then the response status code should be 302
    And I should be redirected to "/organizations/pricing?error=billing_not_configured"

  Scenario: A checkout failure is shown on the pricing page
    Given I am the owner of the workspace "Acme" on the "free" plan
    And the billing client is failing
    When I choose the price "price_pro_month"
    Then the response status code should be 302
    And I should be redirected to a URL starting with "/organizations/pricing?error="

  Scenario: The upgrade preview shows the proration
    Given I am the owner of the workspace "Acme" on the "starter" plan
    And the workspace has an active subscription "sub_1"
    And upgrading to "price_pro_month" would cost 1500 cents after a credit of 400 cents
    When I preview the upgrade to "price_pro_month"
    Then the response status code should be 200
    And the response JSON "success" should be "True"
    And the response JSON "new_plan_name" should be "Pro"
    And the response JSON "total" should be "1500"

  Scenario: The upgrade preview needs a subscription
    Given I am the owner of the workspace "Acme" on the "free" plan
    When I preview the upgrade to "price_pro_month"
    Then the response JSON "has_subscription" should be "False"

  Scenario: Upgrading an existing subscription applies the proration
    Given I am the owner of the workspace "Acme" on the "starter" plan
    And the workspace has an active subscription "sub_1"
    And upgrades succeed
    When I upgrade to "price_pro_month"
    Then the response status code should be 302
    And I should be redirected to "/organizations/pricing?success=true&upgraded=true"
    And the subscription "sub_1" should have been upgraded to "price_pro_month"

  Scenario: Upgrading without a subscription starts a checkout
    Given I am the owner of the workspace "Acme" on the "free" plan
    When I upgrade to "price_pro_month"
    Then the response status code should be 303
    And I should be redirected to "https://checkout.example.test/session"

  Scenario: Administrators see the workspace settings
    Given I am the owner of the workspace "Acme" on the "free" plan
    When I open "/organizations/settings"
    Then the response status code should be 200
    And the page should say "Acme"

  Scenario: Regular members cannot see the workspace settings
    Given I am a regular member of the workspace "Acme" on the "free" plan
    When I open "/organizations/settings"
    Then the response status code should be 403

  Scenario: Renaming the workspace
    Given I am the owner of the workspace "Acme" on the "free" plan
    When I rename the workspace to "Acme Corp"
    Then the response status code should be 302
    And I should be redirected to "/organizations/settings"
    And the workspace should be named "Acme Corp"

  Scenario: Regular members cannot rename the workspace
    Given I am a regular member of the workspace "Acme" on the "free" plan
    When I rename the workspace to "Hijacked"
    Then the response status code should be 403
    And the workspace should be named "Acme"

  Scenario: The legacy tenants prefix serves the same pages
    Given I am the owner of the workspace "Acme" on the "free" plan
    When I open "/tenants/settings"
    Then the response status code should be 200
