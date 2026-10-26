@browser @database
Feature: Package dashboard in a browser
  Signed-in users upload, share and delete their packages from the browser.

  Background:
    Given the repository serves components "main,private" of which "main" is public
    And the identity provider knows these users
      | email             | name  | password |
      | ada@example.com   | Ada   | secret   |
      | grace@example.com | Grace | secret   |
    And the browser catalog has these packages
      | name   | owner             | visibility | component |
      | mine   | ada@example.com   | private    | private   |
      | theirs | grace@example.com | public     | main      |

  Scenario: A visitor is sent to the identity provider
    When I navigate to "/dashboard"
    Then the URL should contain "/oauth2/authorize"
    And I should see "Sign in"

  Scenario: The dashboard only lists the packages of the signed-in user
    Given I sign in as "ada@example.com"
    When I navigate to "/dashboard"
    Then the page title should contain "My Packages"
    And I should see "mine"
    And I should not see "theirs"
    And the navigation should contain a link "My Packages"
    And the navigation should contain a link "Upload"
    And the browser should report no errors

  Scenario: The dashboard can be filtered by name
    Given I sign in as "ada@example.com"
    When I navigate to "/dashboard"
    And I fill "Search by name" with "zzz"
    And I click "Filter"
    Then I should see "You have no packages matching these filters"
    And "mine" should be hidden

  Scenario: A package is uploaded in chunks
    Given the upload chunk size is 1024 bytes
    And I sign in as "ada@example.com"
    When I navigate to "/dashboard/upload"
    And I choose the package file "form-tool" version "2.0" of 3000 bytes
    And I select "Public" from "Visibility"
    And I click "Upload"
    Then I should see "uploaded successfully"
    And the URL should be "/dashboard"
    And I should see "form-tool"
    And the file was sent in as many chunks as the chunk size requires
    And the browser should report no errors

  Scenario: A file that is not a package is reported
    Given I sign in as "ada@example.com"
    When I navigate to "/dashboard/upload"
    And I choose a file "broken.deb" that is not a package
    And I click "Upload"
    Then I should see "Upload failed"
    And the URL should be "/dashboard/upload"

  Scenario: The owner reaches the share page from the package page
    Given I sign in as "ada@example.com"
    When I visit the detail page of the package "mine"
    Then I should see "Share / Manage access"
    When I click "Share / Manage access"
    Then the URL should contain "/share"

  Scenario: Other users get no controls on the package page
    Given I sign in as "ada@example.com"
    When I visit the detail page of the package "theirs"
    Then I should see "sudo apt install theirs"
    And I should not see "Share / Manage access"

  Scenario: A package is shared with another user
    Given I sign in as "ada@example.com"
    When I navigate to "/dashboard"
    And I click "Share"
    Then the URL should contain "/share"
    And I should see "No one else has access to this package"
    When I fill "User ID or Group name" with "grace@example.com"
    And I click "Grant"
    Then I should see "grace@example.com"
    And I should not see "No one else has access"
    And the browser should report no errors

  Scenario: Sharing twice with the same user reports a conflict
    Given I sign in as "ada@example.com"
    And I visit the share page of the package "mine"
    When I fill "User ID or Group name" with "grace@example.com"
    And I click "Grant"
    And I fill "User ID or Group name" with "grace@example.com"
    And I click "Grant"
    Then I should see "This grant already exists"

  Scenario: The user a package is shared with can read it
    Given I sign in as "ada@example.com"
    And I visit the share page of the package "mine"
    When I fill "User ID or Group name" with "grace@example.com"
    And I click "Grant"
    And I visit "/logout"
    And I start from a browser without cookies
    And I sign in as "grace@example.com"
    And I navigate to "/"
    Then I should see "mine"
    When I navigate to "/dashboard"
    Then I should see "theirs"
    And I should not see "mine"
    When I visit the share page of the package "mine"
    Then the page answers 403

  Scenario: Access is revoked after a confirmation
    Given I sign in as "ada@example.com"
    And I visit the share page of the package "mine"
    And I fill "User ID or Group name" with "grace@example.com"
    And I click "Grant"
    When the next confirmation dialog is accepted and says "Revoke access?"
    And I click "Revoke"
    Then the confirmation asked "Revoke access?"
    And I should see "No one else has access to this package"

  Scenario: The visibility of a package is changed
    Given I sign in as "ada@example.com"
    And I visit the share page of the package "mine"
    When I select "Public" from "Visibility"
    And I click "Update"
    Then I should see "Visible to everyone with access to the private component"
    When I navigate to "/dashboard"
    Then I should see "public"

  Scenario: A package is deleted after a confirmation
    Given I sign in as "ada@example.com"
    When I navigate to "/dashboard"
    And the next confirmation dialog is accepted and says "Delete mine 1.0?"
    And I click "Delete"
    Then the confirmation asked "Delete mine 1.0?"
    And I should see "You have no packages"

  Scenario: Cancelling the confirmation keeps the package
    Given I sign in as "ada@example.com"
    When I navigate to "/dashboard"
    And the next confirmation dialog is dismissed
    And I click "Delete"
    Then the confirmation asked "Delete mine 1.0?"
    And I should see "mine"
