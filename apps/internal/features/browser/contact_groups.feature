@browser
Feature: Contact groups in a browser
  As an operator with the contacts permissions
  I want to manage contact groups and their members
  So that I can organize contacts into logical groups

  Background:
    Given the contact groups list returns groups
    And a contact group exists with id "1"
    And contacts not in group "1" returns data

  # --- Access and sidebar ---

  Scenario: The groups are listed
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups"
    Then the page title should be "Contact Groups - Internal Admin"
    And I should see "Newsletter"
    And the sidebar menu should highlight only "Contact Groups"
    And the browser should report no errors

  Scenario: The Contact Groups link leads to the list
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups/new"
    Then the sidebar menu should highlight only "Contact Groups"
    When I follow the sidebar link "Contact Groups"
    Then the URL should be "/contact-groups"

  Scenario: A user without the contacts scope gets the access denied page
    Given I sign in with the scopes "analytics:read"
    When I navigate to "/contact-groups"
    Then the page title should contain "Access Denied"
    And I should see "contacts:read"

  Scenario: An anonymous visitor comes back to the page asked for after the login
    Given a user holding the scopes "contacts:*" exists at the provider
    When I navigate to "/contact-groups/1"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/contact-groups/1"
    And I should see "Newsletter subscribers"

  Scenario: Searching the groups keeps the search in the address
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups"
    And I fill "search" with "R&D"
    And I click "Search"
    Then the URL should contain "search=R%26D"

  # --- Creating and editing ---

  Scenario: A group is created from the form
    Given creating a contact group succeeds
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups"
    And I click "New Group"
    Then the URL should be "/contact-groups/new"
    When I fill "Group Name *" with "VIP Customers"
    And I fill "Slug" with "vip-customers"
    And I fill "Description" with "High-value customers"
    And I click "Create Group"
    Then the URL should contain "/contact-groups?success="
    And I should see "Group created successfully"

  Scenario: A group the mailler service refuses is reported on the form
    Given creating a contact group fails
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups/new"
    And I fill "Group Name *" with "Bad Group"
    And I click "Create Group"
    Then the URL should contain "/contact-groups/new?error="
    And I should see "Failed to create group"

  Scenario: The slug is derived from the name while typing
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups/new"
    And I fill "Group Name *" with "Big Spenders"
    And I press "Tab"
    Then the field "Slug" should contain "big-spenders"

  Scenario: A group is updated from its edit form
    Given updating a contact group succeeds for id "1"
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups/1"
    And I click "Edit"
    Then the URL should be "/contact-groups/1/edit"
    When I fill "Group Name *" with "Updated Group"
    And I click "Update Group"
    Then the URL should contain "/contact-groups/1?success="
    And I should see "Group updated successfully"

  Scenario: A group the mailler service cannot update is reported on the form
    Given updating a contact group fails for id "1"
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups/1/edit"
    And I click "Update Group"
    Then I should see "Failed to update group"

  Scenario: A group that does not exist sends the user back to the list
    Given a contact group does not exist
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups/404"
    Then the URL should contain "/contact-groups?error="
    And I should see "Group not found"

  # --- Members ---

  Scenario: The detail of a group lists its members
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups"
    And I click "Newsletter"
    Then the URL should be "/contact-groups/1"
    And I should see "test@example.com"
    And the sidebar menu should highlight only "Contact Groups"

  Scenario: The members are added to a group from the list of the other contacts
    Given adding contacts to group "1" succeeds
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups/1"
    And I click "Add Contacts" in the page content
    Then the URL should be "/contact-groups/1/add-contacts"
    When I click "css=.contact-checkbox"
    And I click "Add to Group"
    Then the URL should contain "/contact-groups/1?success="
    And I should see "3 contact(s) added"

  Scenario: The error of a refused addition is shown on the page
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups/1/add-contacts?error=No+contacts+selected"
    Then I should see "No contacts selected"

  Scenario: A member is removed from a group
    Given removing contacts from group "1" succeeds
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups/1"
    And I click "Remove" in the page content
    Then the URL should contain "/contact-groups/1?success="
    And I should see "2 contact(s) removed"

  # --- Deleting ---

  Scenario: A group is deleted from its page after a confirmation
    Given deleting contact group "1" succeeds
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups/1"
    And I click "Delete Group"
    Then the page should have asked for a confirmation containing "delete this group"
    And the URL should contain "/contact-groups?success="
    And I should see "Group deleted successfully"

  Scenario: A group is deleted from its edit form after a confirmation
    Given deleting contact group "1" succeeds
    And updating a contact group succeeds for id "1"
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups/1/edit"
    And I click "Delete" in the page content
    Then the page should have asked for a confirmation containing "delete this group"
    And the URL should contain "/contact-groups?success="
    And I should see "Group deleted successfully"
    And the mailler service should not have updated the group

  Scenario: Selected groups are deleted in bulk
    Given bulk deleting contact groups succeeds
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contact-groups"
    And I click "css=.row-checkbox"
    And I click "Delete Selected"
    Then I should see "group(s) deleted successfully"
