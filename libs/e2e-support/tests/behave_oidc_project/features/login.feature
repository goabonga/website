@browser
Feature: Signing in through OpenID Connect

  Scenario: Anonymous visitors are sent to the provider
    When I navigate to "/dashboard"
    Then the URL should contain "/oauth2/authorize"
    And I should see "Sign in to continue to"

  Scenario: A user signs in and lands on the dashboard
    When I navigate to "/dashboard"
    And I fill "Email" with "ada@example.test"
    And I fill "Password" with "secret"
    And I click "Sign in"
    Then the URL should be "/dashboard"
    And I should see "Welcome Ada"
    And I should see "ada@example.test"
    And the provider received a token request for the "authorization_code" grant
    And the browser should report no errors

  Scenario: The scopes of the user decide what the navigation shows
    When I navigate to "/dashboard"
    And I fill "Email" with "ada@example.test"
    And I fill "Password" with "secret"
    And I click "Sign in"
    Then the navigation should contain a link "Billing"
    And the provider received a token request for the "urn:ietf:params:oauth:grant-type:token-exchange" grant

  Scenario: A user without the billing scope does not see the link
    When I navigate to "/dashboard"
    And I fill "Email" with "grace@example.test"
    And I fill "Password" with "secret"
    And I click "Sign in"
    Then I should see "Welcome Grace"
    And the navigation should not contain a link "Billing"

  Scenario: A wrong password keeps the user on the login page
    When I navigate to "/dashboard"
    And I fill "Email" with "ada@example.test"
    And I fill "Password" with "wrong"
    And I click "Sign in"
    Then I should see "Invalid email or password."
    And the URL should contain "/oauth2/authorize/login"

  @auto-approve
  Scenario: With auto-approve the login page is skipped
    When I navigate to "/dashboard"
    Then the URL should be "/dashboard"
    And I should see "Welcome Ada"
    And the provider never showed a login page

  Scenario: Signing out ends the session at the application
    When I navigate to "/dashboard"
    And I fill "Email" with "ada@example.test"
    And I fill "Password" with "secret"
    And I click "Sign in"
    And I click "Sign out"
    Then the URL should be "/"

  Scenario: Revoked tokens send the user back to the provider
    When I navigate to "/dashboard"
    And I fill "Email" with "ada@example.test"
    And I fill "Password" with "secret"
    And I click "Sign in"
    And the provider ends every session
    And I navigate to "/dashboard"
    Then the URL should contain "/oauth2/authorize"
    And I should see "Sign in to continue to"
