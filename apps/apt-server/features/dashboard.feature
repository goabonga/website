Feature: Package dashboard
  Signed-in users upload, share and delete their packages from the browser.

  Background:
    Given the repository serves components "main,private" of which "main" is public

  @database
  Scenario: Visitors are sent to the login page
    Given I am an anonymous apt caller
    When I open the dashboard without following redirects
    Then the response status is 302
    And the response redirects to "/login"

  @database
  Scenario: Users upload a package from the form
    Given I am the signed-in user "alice"
    When I submit the upload form with the package "form-tool" version "1.0"
    Then the response status is 303
    And the dashboard lists "form-tool"

  @database
  Scenario: The dashboard only lists my own packages
    Given a catalog with these indexed packages
      | name   | owner | visibility | component |
      | mine   | alice | private    | main      |
      | theirs | bob   | public     | main      |
    And I am the signed-in user "alice"
    Then the dashboard lists "mine"
    And the dashboard does not list "theirs"

  @database
  Scenario: Sharing a package grants access to another user
    Given a catalog with these indexed packages
      | name | owner | visibility | component |
      | mine | alice | private    | main      |
    And I am the signed-in user "alice"
    When I share the package "mine" with user "bob"
    Then the response status is 303
    And the package "mine" is shared with "bob"

  @database
  Scenario: Sharing twice with the same user reports a conflict
    Given a catalog with these indexed packages
      | name | owner | visibility | component |
      | mine | alice | private    | main      |
    And I am the signed-in user "alice"
    When I share the package "mine" with user "bob"
    And I share the package "mine" with user "bob"
    Then the response status is 409

  @database
  Scenario: Users cannot delete packages they do not own
    Given a catalog with these indexed packages
      | name | owner | visibility | component |
      | mine | alice | public     | main      |
    And I am the signed-in user "mallory"
    When I delete the package "mine" from the dashboard
    Then the response status is 403

  @database
  Scenario: Owners delete their package
    Given a catalog with these indexed packages
      | name | owner | visibility | component |
      | mine | alice | private    | main      |
    And I am the signed-in user "alice"
    When I delete the package "mine" from the dashboard
    Then the response status is 303
    And the dashboard does not list "mine"
