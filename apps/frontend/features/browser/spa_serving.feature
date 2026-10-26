@browser
Feature: Single page application in a browser
  The page rendered by the server boots the web client built from the sources:
  the injected configuration, the static files and the routes are checked in
  Chromium, with the browser console watched.

  Background:
    Given the web client is built

  Scenario: The application page boots the web client
    Given the application is running
    When I navigate to "/"
    Then the page title should be "GOABONGA"
    And "MENU" should be visible
    And the browser should report no errors

  Scenario: The runtime settings reach the web client
    Given the setting "app_name" is "Atelier"
    And the setting "auth_url" is "https://auth.test"
    And the setting "api_url" is "https://api.test"
    And the setting "oauth2_client_id" is "client-123"
    And the setting "welcome_name" is "Ada"
    And the setting "welcome_words" is "one,two,three"
    And the application is running
    When I navigate to "/"
    Then the page title should be "Atelier"
    And the web client configuration "appName" is "Atelier"
    And the web client configuration "authUrl" is "https://auth.test"
    And the web client configuration "apiUrl" is "https://api.test"
    And the web client configuration "clientId" is "client-123"
    And the web client configuration "welcomeName" is "Ada"
    And the web client configuration "welcomeWords" is "one,two,three"
    And I should see "I'm Ada"
    And the browser should report no errors

  Scenario: Settings with special characters reach the web client unchanged
    Given the setting "app_name" is "Café <Atelier>"
    And the setting "legal_company_name" is "O'Brien & Sons"
    And the setting "auth_url" is "https://auth.test/start?a=1&b=2"
    And the application is running
    When I navigate to "/"
    Then the page title should be "Café <Atelier>"
    And the web client configuration "appName" is "Café <Atelier>"
    And the web client configuration "legal.companyName" is "O'Brien & Sons"
    And the web client configuration "authUrl" is "https://auth.test/start?a=1&b=2"
    And the browser should report no errors

  Scenario: The static files of the build are served with the page
    Given the application is running
    When I navigate to "/"
    Then "MENU" should be visible
    And the browser loaded "/static/assets/index.js" as "javascript"
    And the browser loaded "/static/assets/index.css" as "text/css"

  Scenario Outline: Every path is served by the catch-all
    Given the application is running
    When I navigate to "<path>"
    Then the page title should be "GOABONGA"
    And "MENU" should be visible
    And the browser should report no errors

    Examples:
      | path               |
      | /                  |
      | /pricing           |
      | /a/very/deep/route |
      | /login             |

  Scenario: The web client handles its own callback route
    Given the application is running
    When I navigate to "/auth/callback?code=abc&state=forged"
    Then I should see "Invalid state parameter"

  Scenario: Missing static files are reported as not found
    Given the application is running
    When I visit "/static/assets/missing.js"
    Then the page answers 404

  Scenario: The health check is not shadowed by the application page
    Given the application is running
    When I visit "/health"
    Then the page answers 200
    And I should see "healthy"
    And I should not see "MENU"

  Scenario: The menu lists the profile links of the settings
    Given the setting "social_github" is "https://github.test/ada"
    And the setting "social_linkedin" is "https://linkedin.test/in/ada"
    And the application is running
    When I navigate to "/"
    And I click "MENU"
    Then the navigation link "GitHub" should point to "https://github.test/ada"
    And the navigation link "LinkedIn" should point to "https://linkedin.test/in/ada"

  Scenario: The legal notice shows the publisher and the host of the settings
    Given the setting "legal_company_name" is "ACME Ltd"
    And the setting "legal_director_name" is "Jane Doe"
    And the setting "legal_host_name" is "Hosting Inc"
    And the setting "legal_host_phone" is "555 0100"
    And the application is running
    When I navigate to "/"
    Then "Legal Notice" should be hidden
    When I click "Policies"
    Then I should see "Legal Notice"
    And I should see "ACME Ltd"
    And I should see "Jane Doe"
    And I should see "Hosting Inc"
    And I should see "Phone: 555 0100"
    When I click "CLOSE"
    Then "Legal Notice" should be hidden

  Scenario: Without a client build the page opens but the web client cannot start
    Given the setting "static_dir" is "/nonexistent/build"
    And the application is running
    When I navigate to "/"
    Then the page title should be "GOABONGA"
    And the browser loaded "/static/assets/index.js" as "text/html"
    And the browser reported an error matching "module script"
    And "MENU" should be hidden
