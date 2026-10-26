@browser
Feature: Checkout URL allow-list and branding of billing SaaS apps in a browser
  As an administrator of the billing platform
  I want to declare where each SaaS app may send its customers back to, and how its checkout looks
  So that Stripe only redirects to URLs the app accepts

  Scenario: The new SaaS app form offers the allow-list and the branding
    Given I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/new"
    Then I should see "Checkout URL allow-list"
    And I should see "Branding (JSON)"

  Scenario: A SaaS app is created with a checkout URL allow-list and a branding
    Given the billing service saves the SaaS app
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/new"
    And I fill "Name" with "My SaaS"
    And I fill "Slug" with "my-saas"
    And I fill "Checkout URL allow-list" with "https://app.example.test"
    And I fill "Branding (JSON)" with the text '{"locale": "xx"}'
    And I click "Create SaaS App"
    Then the URL should contain "/billing/saas/saas-new?success="
    And the SaaS app should have been created with the checkout URLs "https://app.example.test"
    And the SaaS app should have been created with the branding '{"locale": "xx"}'

  Scenario: Several checkout URLs are given one per line
    Given the billing service saves the SaaS app
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/new"
    And I fill "Name" with "My SaaS"
    And I fill "Slug" with "my-saas"
    And I fill "Checkout URL allow-list" with the following lines
      """
      https://a.example.test
      https://b.example.test/pay
      """
    And I click "Create SaaS App"
    Then the SaaS app should have been created with the checkout URLs "https://a.example.test,https://b.example.test/pay"

  Scenario: A checkout URL without scheme is refused and the user stays on the form
    Given the billing service saves the SaaS app
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/new"
    And I fill "Name" with "My SaaS"
    And I fill "Slug" with "my-saas"
    And I fill "Checkout URL allow-list" with "app.example.test"
    And I click "Create SaaS App"
    Then the URL should contain "/billing/saas/new?error="
    And I should see "is not an absolute http(s) URL"
    And no SaaS app should have been created

  Scenario: A checkout URL with a query string is refused on the edit form
    Given a SaaS app exists with id "saas-1"
    And the billing service saves the SaaS app
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/edit"
    And I fill "Checkout URL allow-list" with "https://app.example.test/?utm=1"
    And I click "Update SaaS App"
    Then the URL should contain "/billing/saas/saas-1/edit?error="
    And I should see "must not contain credentials, a query or a fragment"
    And no SaaS app should have been updated

  Scenario: A branding that is not a JSON object is refused
    Given the billing service saves the SaaS app
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/new"
    And I fill "Name" with "My SaaS"
    And I fill "Slug" with "my-saas"
    And I fill "Branding (JSON)" with "[1, 2]"
    And I click "Create SaaS App"
    Then I should see "Branding must be a JSON object"
    And no SaaS app should have been created

  Scenario: The edit form shows the current allow-list and branding
    Given the SaaS app "saas-1" accepts the checkout URLs "https://a.example.test,https://b.example.test/pay" and has the branding '{"locale": "xx"}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/edit"
    Then the field "Checkout URL allow-list" should contain "https://b.example.test/pay"
    And the field "Branding (JSON)" should contain "locale"

  Scenario: Emptying the fields on the edit form clears them
    Given the SaaS app "saas-1" accepts the checkout URLs "https://a.example.test" and has the branding '{"locale": "xx"}'
    And the billing service saves the SaaS app
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1/edit"
    And I clear "Checkout URL allow-list"
    And I clear "Branding (JSON)"
    And I click "Update SaaS App"
    Then the URL should contain "success="
    And the SaaS app should have been updated with no checkout URL and no branding

  Scenario: The page of the SaaS app shows the allow-list and the branding
    Given the SaaS app "saas-1" accepts the checkout URLs "https://a.example.test" and has the branding '{"locale": "xx"}'
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1"
    Then I should see "https://a.example.test"
    And I should see "locale"

  Scenario: The page of the SaaS app says when redirects are refused
    Given the SaaS app "saas-1" has no checkout URL and no branding
    And I sign in with the scopes "billing:*"
    When I navigate to "/billing/saas/saas-1"
    Then I should see "checkout and portal redirects are refused"
