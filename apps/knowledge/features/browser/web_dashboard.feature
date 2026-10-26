@browser
Feature: Landing, dashboard, pricing and download pages in a browser
  As a visitor or a signed-in user
  I want public pages and a dashboard of my workspace
  So that I can discover the product, see my usage and download the MCP

  Scenario: A visitor discovers the product and goes on to sign up
    When I navigate to "/"
    Then I should see "Vector Storage"
    And the page title should contain "Knowledge"
    When I click "Get Started"
    Then the URL should be "/auth/signup"
    And I should see "Create your account"

  Scenario: The landing page leads to the sign-in page and the legal pages
    When I navigate to "/"
    And I click "Sign In"
    Then the URL should be "/auth/signin"
    When I navigate to "/"
    And I click "Terms of Service"
    Then the URL should be "/terms"
    And I should see "Acceptance of Terms"
    When I click "Privacy Policy"
    Then the URL should be "/privacy"
    When I click "Legal Notice"
    Then the URL should be "/legal"
    And I should see "Example Operator"

  Scenario: Signed-in users are sent to their dashboard
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/"
    Then the URL should be "/dashboard"

  Scenario: The public pages know that the visitor is signed in
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/pricing"
    Then I should not see "Get Started"
    And the navigation should contain a link "Dashboard"
    When I navigate to "/mcp"
    Then the navigation should contain a link "Dashboard"
    When I navigate to "/terms"
    Then the navigation should contain a link "Dashboard"
    And the navigation should not contain a link "Sign In"

  Scenario: Every public page links back to the landing page
    When I navigate to "/pricing"
    And I click "Knowledge."
    Then the URL should be "/"
    When I navigate to "/mcp"
    And I click "Knowledge."
    Then the URL should be "/"

  Scenario: The pricing page lists the plans of the billing service
    Given the billing service offers the plan "Starter" at 900 cents a month or 9000 cents a year
    And the billing service offers the plan "Pro" at 2900 cents a month or 29000 cents a year
    When I navigate to "/pricing"
    Then I should see "Starter"
    And I should see "Pro"
    And I should see "$9"
    When I click "Yearly"
    Then I should see "Save 17%"
    And the browser should report no errors

  Scenario: The pricing page tells when the plans cannot be loaded
    Given the billing service refuses every request
    When I navigate to "/pricing"
    Then I should see "Unable to load pricing"

  Scenario: The dashboard requires a signed-in user
    When I navigate to "/dashboard"
    Then I should be at the identity provider

  Scenario: The dashboard shows the usage of the workspace
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And the workspace "Acme" contains the collection "Handbook"
    And the workspace "Acme" contains the collection "Runbooks"
    And the collection "Handbook" contains the document "How to deploy the service"
    And I have signed in as "Alice" through the identity provider
    Then I should see "Welcome back, Alice"
    And the dashboard should display 2 collections and 1 documents
    And I should see "Handbook"
    And the page title should be "Dashboard - Knowledge API"

  Scenario: The MCP download page tells when there is no release
    When I navigate to "/mcp"
    Then I should see "No Releases Available"

  Scenario: The MCP download page offers the binaries of the latest release
    Given the release "1.4.0" is published with a binary for "linux-x86_64"
    When I navigate to "/mcp"
    Then I should see "1.4.0"
    When I download the "linux-x86_64" binary
    Then the browser should be sent to the release host
    And the release "1.4.0" was downloaded 1 time for "linux-x86_64"

  Scenario: Signing in through the identity provider lands on the dashboard
    Given a user "Alice" who holds every knowledge scope
    When I navigate to "/auth/login"
    And I sign in as "Alice" at the identity provider
    Then the URL should be "/dashboard"
    And I should see "Welcome back, Alice"
    And the workspace "Alice's Workspace" should exist on the "free" plan
    And the browser should report no errors

  Scenario: A new user lands on the dashboard of the workspace they named
    When I navigate to "/auth/signup"
    And I click "Continue"
    And I fill "Nickname" with "ada"
    And I fill "First Name" with "Ada"
    And I fill "Last Name" with "Lovelace"
    And I fill "Workspace name" with "Analytical Engines"
    And I fill "Email address" with "ada@example.test"
    And I fill "Password" with "Long-passphrase-1!"
    And I fill "Confirm password" with "Long-passphrase-1!"
    And I click "Create Account"
    And I enter the verification code sent to "ada@example.test"
    And I fill "Email address" with "ada@example.test"
    And I fill "Password" with "Long-passphrase-1!"
    And I click "Sign In"
    Then the URL should be "/dashboard"
    And I should see "Welcome back, Ada Lovelace"
    And I should see "Analytical Engines"
    And the browser should report no errors

  Scenario: Signing out leads back to the landing page
    Given a user "Alice" who holds every knowledge scope
    And I have signed in as "Alice" through the identity provider
    When I click "Logout"
    Then the URL should be "/"
    And I should see "Sign In"
    And the browser should not hold the cookie "access_token"
    And the browser should not hold the cookie "active_tenant_id"

  Scenario: The pages before the sign-in only lead to pages that exist
    When I navigate to "/auth/signin"
    Then every link of the page leads to a page of the application
    When I navigate to "/auth/signup"
    Then every link of the page leads to a page of the application
    When I navigate to "/auth/forgot-password"
    Then every link of the page leads to a page of the application

  Scenario Outline: The public pages only lead to pages that exist
    When I navigate to "<path>"
    Then every link of the page leads to a page of the application

    Examples:
      | path     |
      | /        |
      | /pricing |
      | /mcp     |
      | /legal   |
      | /privacy |
      | /terms   |

  Scenario: The sidebar of the dashboard only lists the pages that exist
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And I have signed in as "Alice" through the identity provider
    Then the sidebar item "Dashboard" should be the active one
    And every link of the navigation leads to a page of the application
    And every link of the page leads to a page of the application
