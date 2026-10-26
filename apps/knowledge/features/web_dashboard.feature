Feature: Landing, dashboard, pricing and download pages
  As a visitor or a signed-in user
  I want public pages and a dashboard of my workspace
  So that I can discover the product, see my usage and download the MCP

  Background:
    Given the web pages database is in memory

  Scenario: Visitors see the landing page
    When I open "/"
    Then the response status code should be 200
    And the page should say "Vector Storage"

  Scenario: Signed-in users are sent to their dashboard
    When I open "/" carrying an access token
    Then the response status code should be 302
    And I should be redirected to "/dashboard"

  Scenario Outline: Legal pages are public
    When I open "<path>"
    Then the response status code should be 200
    And the page should say "<title>"

    Examples:
      | path     | title                |
      | /legal   | Legal Notice         |
      | /privacy | Privacy Policy       |
      | /terms   | Terms of Service     |

  Scenario: The pricing page lists the plans of the billing service
    Given the billing service offers the plans "Starter" at 900 cents and "Pro" at 2900 cents per month
    When I open "/pricing"
    Then the response status code should be 200
    And the page should say "Starter"
    And the page should say "Pro"

  Scenario: The pricing page reports a billing failure
    Given the billing service is failing
    When I open "/pricing"
    Then the response status code should be 200
    And the page should say "Unable to load pricing"

  Scenario: The dashboard requires a signed-in user
    When I open "/dashboard"
    Then the response status code should be 302
    And I should be redirected to a URL starting with "/auth/login"

  Scenario: The dashboard shows the usage of the workspace
    Given I am signed in as "Alice" in the workspace "Acme" on the "free" plan
    And the workspace holds 2 collections and 12 documents
    When I open "/dashboard"
    Then the response status code should be 200
    And the page should say "Welcome back, Alice"
    And the dashboard should count 2 collections and 12 documents

  Scenario: A user without workspace is invited to create one
    Given I am signed in as "Alice" without a workspace
    When I open "/dashboard"
    Then the response status code should be 200
    And the page should say "Welcome back, Alice"

  Scenario: The download page lists the published releases
    Given the release "1.0.0" published on "2026-01-01T00:00:00Z" for "linux-x86_64"
    And the release "1.1.0" published on "2026-02-01T00:00:00Z" for "linux-x86_64,macos-arm64"
    When I open "/mcp/downloads"
    Then the response status code should be 200
    And the page should say "v1.1.0"
    And the page should say "/api/v1/mcp/download/1.1.0/macos-arm64"

  Scenario: The download page works without any release
    When I open "/mcp"
    Then the response status code should be 200
