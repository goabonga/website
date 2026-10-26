Feature: Public web pages
  Visitors browse the packages they may see, read the client setup guide and
  open the detail page of a package.

  Background:
    Given the repository serves components "main,private" of which "main" is public
    And a catalog with these indexed packages
      | name   | owner | visibility | component |
      | tool   | alice | public     | main      |
      | secret | alice | private    | private   |

  @database
  Scenario: The home page lists public packages
    When I request "/"
    Then the response status is 200
    And the response body contains "tool"
    And the response body does not contain "secret"

  @database
  Scenario: The package list can be searched
    When I request "/?q=zzz"
    Then the response status is 200
    And the response body contains "No packages visible"

  @database
  Scenario: The setup page explains how to register the repository
    When I request "/setup"
    Then the response status is 200
    And the response body contains "pubkey.gpg"
    And the response body contains "apt update"

  @database
  Scenario: A public package has a detail page
    When I open the detail page of package "tool"
    Then the response status is 200
    And the response body contains "sudo apt install tool=1.0"

  @database
  Scenario: A private package detail page is hidden from visitors
    When I open the detail page of package "secret"
    Then the response status is 404

  @database
  Scenario: Owners see their private packages on the home page
    Given I am the apt caller "alice" with scopes "apt:read"
    When I request "/"
    Then the response body contains "secret"
