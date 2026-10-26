@browser
Feature: Generic browser steps

  Scenario: Signing in with a labelled form
    Given I navigate to "/login"
    When I fill "Email" with "ada@example.test"
    And I fill "Your password" with "secret"
    And I select "Editor" from "Role"
    And I click "Sign in"
    Then the URL should be "/dashboard"
    And the URL should contain "dash"
    And the page title should be "Dashboard"
    And the page title should contain "Dash"
    And I should see "Welcome back"
    And I should not see "Never shown"
    And "Welcome back" should be visible
    And "Never shown" should be hidden
    And "css=nav" should be visible
    And the browser should report no errors

  Scenario: A wrong password shows an error
    Given I navigate to "/login"
    When I fill "css=#password" with "nope"
    And I press "Enter"
    Then I should see "Invalid credentials"
    And the URL should contain "/login"

  Scenario: The navigation of the dashboard
    Given I navigate to "/dashboard"
    Then the navigation should contain a link "Settings"
    And the navigation link "Settings" should point to "/settings"
    And the navigation should not contain a link "Sign out"
    And the navigation should not contain a link "Billing"

  Scenario: Steps wait for elements that appear later
    Given I navigate to "/delayed"
    When I click "Reveal"
    And I click "Later"
    Then the page title should be "Clicked later"

  Scenario: Taking a screenshot
    Given I navigate to "/dashboard"
    When I take a screenshot "Dashboard home"
    Then I should see "Welcome back"

  @fails
  Scenario: A step that cannot find its target fails with a clear message
    Given I navigate to "/dashboard"
    When I click "Nonexistent button"
