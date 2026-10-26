@browser @database
Feature: Public web pages in a browser
  Visitors browse the packages they may see, read the setup guide and open a
  package; signing in from the pages shows the private ones.

  Background:
    Given the repository serves components "main,private" of which "main" is public
    And the identity provider knows these users
      | email           | name | password |
      | ada@example.com | Ada  | secret   |
    And the browser catalog has these packages
      | name   | owner           | visibility | component |
      | tool   | ada@example.com | public     | main      |
      | secret | ada@example.com | private    | private   |

  Scenario: The home page lists the public packages to a visitor
    When I navigate to "/"
    Then the page title should contain "Packages"
    And I should see "tool"
    And I should not see "secret"
    And I should see "Showing public packages only"
    And the navigation should contain a link "Setup"
    And the navigation should not contain a link "My Packages"
    And the component filter offers only "All components, main"
    And the browser should report no errors

  Scenario: The package list can be filtered by name
    When I navigate to "/"
    And I fill "Search by name" with "zzz"
    And I click "Filter"
    Then the URL should contain "q=zzz"
    And I should see "No packages visible with the current filters"
    And "tool" should be hidden

  Scenario: The package list is paginated
    Given 30 public packages named "bulk" exist
    When I navigate to "/"
    Then I should see "page 1 of 2"
    When I click "Next"
    Then the URL should contain "page=2"
    And I should see "page 2 of 2"
    And I should see "Previous"

  Scenario: The setup guide explains how to register the repository
    When I navigate to "/"
    And I click "Setup"
    Then the URL should be "/setup"
    And I should see "pubkey.gpg"
    And I should see "apt update"
    And I should see "Sign in to see the private repository setup guide"
    And the browser should report no errors

  Scenario: A public package has a detail page
    When I navigate to "/"
    And I click "tool"
    Then the URL should contain "/packages/"
    And I should see "sudo apt install tool=1.0"
    And I should see "Control stanza"
    And the browser should report no errors

  Scenario: A private package is hidden from visitors
    When I visit the detail page of the package "secret"
    Then the page answers 404

  Scenario: A visitor signs in from the home page
    When I navigate to "/"
    And I click "Sign in"
    And I fill "Email" with "ada@example.com"
    And I fill "Password" with "secret"
    And I click "Sign in"
    Then the URL should be "/"
    And I should see "ada@example.com"
    And I should see "secret"
    And I should not see "Showing public packages only"
    And the component filter offers only "All components, main, private"
    And the browser should report no errors

  Scenario: A signed-in user sees the private repository guide and the owner
    Given I sign in as "ada@example.com"
    When I navigate to "/setup"
    Then I should see "Private repository (PAT)"
    And I should see "ada@example.com:gab_pat_xxxx"
    When I visit the detail page of the package "secret"
    Then I should see "ada@example.com"
    And the browser should report no errors

  Scenario: Signing out brings the sign-in button back
    Given I sign in as "ada@example.com"
    When I navigate to "/"
    And I click "Logout"
    Then the URL should be "/"
    And I should see "Showing public packages only"
    And I should not see "secret"
