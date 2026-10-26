@browser @database
Feature: Web login sessions in a browser
  A visitor signs in at the identity provider and comes back with a session
  cookie that opens the private components; signing out closes them again.

  Background:
    Given the repository serves components "main,private" of which "main" is public
    And the identity provider knows these users
      | email           | name | password |
      | ada@example.com | Ada  | secret   |
    And the browser catalog has these packages
      | name   | owner           | visibility | component |
      | secret | ada@example.com | private    | private   |

  Scenario: Signing in at the identity provider creates a session
    When I sign in as "ada@example.com"
    Then the URL should be "/"
    And the browser holds the cookie "apt_session"
    And the cookie "apt_session" is HTTP only and secure
    And the browser does not hold the cookie "oauth_state"
    And the provider received a token request for the "authorization_code" grant

  Scenario: The session opens the private components
    When I sign in as "ada@example.com"
    And I visit "/dists/stable/private/binary-amd64/Packages"
    Then the page answers 200
    And I should see "Package: secret"

  Scenario: Without a session the private components stay closed
    When I visit "/dists/stable/private/binary-amd64/Packages"
    Then the page answers 401

  Scenario: Signing out closes the private components
    Given I sign in as "ada@example.com"
    When I visit "/logout"
    Then the browser does not hold the cookie "apt_session"
    When I visit "/dists/stable/private/binary-amd64/Packages"
    Then the page answers 401

  Scenario: A wrong password keeps the visitor at the identity provider
    When I navigate to "/login"
    And I fill "Email" with "ada@example.com"
    And I fill "Password" with "not-the-password"
    And I click "Sign in"
    Then I should see "Sign in"
    And the browser does not hold the cookie "apt_session"

  Scenario: A callback that does not follow a login is refused
    When I visit "/callback?code=abc&state=forged"
    Then the page answers 400
    And I should see "missing state cookie"

  Scenario: A forged session cookie is ignored
    Given the browser is given the cookie "apt_session" with the value "forged.cookie"
    When I visit "/dists/stable/private/binary-amd64/Packages"
    Then the page answers 401

  Scenario: A revoked token degrades the session to a visitor
    Given I sign in as "ada@example.com"
    When the provider revokes every token
    And I visit "/dists/stable/private/binary-amd64/Packages"
    Then the page answers 401
