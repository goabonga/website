@browser
Feature: Contact management in a browser
  As an operator with the contacts permissions
  I want to list, search, create, edit, import, export and delete contacts
  So that I can maintain the mailing list

  Background:
    Given the contacts list returns data
    And a contact exists with id "42"

  # --- Access and sidebar ---

  Scenario: The contacts are listed
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    Then the page title should be "Contacts - Internal Admin"
    And I should see "test@example.com"
    And I should see "manual"
    And the sidebar menu should highlight only "Contacts"
    And the browser should report no errors

  Scenario: The Contacts link leads to the list
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/new"
    Then the sidebar menu should highlight only "Contacts"
    When I follow the sidebar link "Contacts"
    Then the URL should be "/contacts"

  Scenario: A user without the contacts scope gets the access denied page
    Given I sign in with the scopes "analytics:read"
    When I navigate to "/contacts"
    Then the page title should contain "Access Denied"
    And I should see "contacts:read"

  Scenario: A user who may only read cannot create or import
    Given I sign in with the scopes "contacts:read"
    When I navigate to "/contacts/new"
    Then the page title should contain "Access Denied"
    And I should see "contacts:write"

  Scenario: An anonymous visitor comes back to the filtered list after the login
    Given a user holding the scopes "contacts:*" exists at the provider
    When I navigate to "/contacts?search=ada&status=active"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/contacts?search=ada&status=active"
    And the mailler service should have been asked for the contacts matching "ada"

  # --- Searching and paginating ---

  Scenario: Searching narrows the list
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    And I fill "search" with "ada"
    And I click "Filter"
    Then the URL should contain "search=ada"
    And the mailler service should have been asked for the contacts matching "ada"

  Scenario: Filtering by status and group
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    And I select "Bounced" from "status"
    And I select "Newsletter" from "group"
    And I click "Filter"
    Then the URL should contain "status=bounced"
    And the URL should contain "group=1"

  Scenario: The list is paginated and keeps the search
    Given the contacts list has 3 pages
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    And I fill "search" with "R&D"
    And I click "Filter"
    And I click "Next →"
    Then the URL should contain "page=2"
    And the mailler service should have been asked for the contacts matching "R&D"

  Scenario: A group that is not a number in the address is ignored
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contacts?group=abc"
    Then I should see "test@example.com"

  # --- Creating ---

  Scenario: A contact is created and put in a group
    Given creating a contact succeeds
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    And I click "New Contact"
    Then the URL should be "/contacts/new"
    When I fill "Email Address *" with "ada@example.com"
    And I fill "First Name" with "Ada"
    And I fill "Last Name" with "Lovelace"
    And I click "css=input[name=group_ids]"
    And I click "Create Contact"
    Then the URL should contain "/contacts?success="
    And I should see "Contact created successfully"
    And the contact "99" should have been added to the group "1"

  Scenario: The form stops an address that is not an email
    Given creating a contact succeeds
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/new"
    And I fill "Email Address *" with "not-an-email"
    And I click "Create Contact"
    Then the URL should be "/contacts/new"
    And the mailler service should not have been asked to create a contact

  Scenario: A contact the mailler service refuses is reported on the form
    Given creating a contact fails
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/new"
    And I fill "Email Address *" with "fail@example.com"
    And I click "Create Contact"
    Then the URL should contain "/contacts/new?error="
    And I should see "Failed to create contact"

  # --- Detail, edit, unsubscribe, delete ---

  Scenario: The list leads to the detail of a contact
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    And I click "test@example.com"
    Then the URL should be "/contacts/42"
    And I should see "Mark as Unsubscribed"
    And the sidebar menu should highlight only "Contacts"

  Scenario: A contact that does not exist sends the user back to the list
    Given a contact does not exist
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/404"
    Then the URL should contain "/contacts?error="
    And I should see "Contact not found"

  Scenario: A contact is updated from its edit form
    Given updating a contact succeeds for id "42"
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/42"
    And I click "Edit Contact"
    Then the URL should be "/contacts/42/edit"
    And the field "Email Address *" should contain "test@example.com"
    When I fill "First Name" with "Renamed"
    And I click "Update Contact"
    Then the URL should contain "/contacts/42?success="
    And I should see "Contact updated successfully"

  Scenario: A contact the mailler service cannot update is reported
    Given updating a contact fails for id "42"
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/42/edit"
    And I click "Update Contact"
    Then I should see "Failed to update contact"

  Scenario: A contact is unsubscribed
    Given unsubscribing a contact succeeds for id "42"
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/42"
    And I click "Mark as Unsubscribed"
    Then the URL should contain "/contacts/42?success="
    And I should see "Contact marked as unsubscribed"

  Scenario: A contact is deleted from its page after a confirmation
    Given deleting a contact succeeds for id "42"
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/42"
    And I click "Delete Contact"
    Then the page should have asked for a confirmation containing "delete this contact"
    And the URL should contain "/contacts?success="
    And I should see "Contact deleted successfully"

  Scenario: A contact is deleted from its edit form after a confirmation
    Given deleting a contact succeeds for id "42"
    And updating a contact succeeds for id "42"
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/42/edit"
    And I click "Delete" in the page content
    Then the page should have asked for a confirmation containing "delete this contact"
    And the URL should contain "/contacts?success="
    And I should see "Contact deleted successfully"
    And the mailler service should not have updated the contact

  Scenario: Dismissing the confirmation keeps the contact
    Given deleting a contact succeeds for id "42"
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/42/edit"
    And I dismiss the next confirmation
    And I click "Delete" in the page content
    Then the URL should be "/contacts/42/edit"
    And the mailler service should not have deleted a contact

  Scenario: A contact the mailler service cannot delete is reported
    Given deleting a contact fails for id "42"
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/42"
    And I click "Delete Contact"
    Then I should see "Failed to delete contact"

  # --- Bulk actions ---

  Scenario: The bulk actions appear when contacts are selected
    Given I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    Then "Delete Selected" should be hidden
    When I click "css=.contact-checkbox"
    Then "Delete Selected" should be visible
    And I should see "1 selected"

  Scenario: Selected contacts are deleted in bulk
    Given bulk deleting contacts succeeds
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    And I click "css=#select-all"
    And I click "Delete Selected"
    Then the page should have asked for a confirmation containing "delete 1 contact(s)"
    And I should see "1 contact(s) deleted"
    And the mailler service should have been asked to delete the contacts "42"

  Scenario: Selected contacts are added to a group in bulk
    Given bulk adding contacts to group succeeds
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    And I click "css=.contact-checkbox"
    And I select "Newsletter" from "css=#bulk-group"
    And I click "Add to Group"
    Then I should see "3 contact(s) added to group"
    And the contact "42" should have been added to the group "1"

  Scenario: Adding to a group needs a group
    Given bulk adding contacts to group succeeds
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    And I click "css=.contact-checkbox"
    And I click "Add to Group"
    Then the page should have alerted "Please select contacts and a group"

  # --- Import and export ---

  Scenario: Contacts are imported from a CSV file
    Given the mailler service imports contacts
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    And I click "Import CSV"
    Then the URL should be "/contacts/import"
    When I choose the file "people.csv" for "CSV File *" with the following content
      """
      email,first_name,last_name
      Ada@Example.com,Ada,Lovelace
      grace@example.com,Grace,Hopper
      """
    And I click "Import Contacts"
    Then the URL should contain "/contacts?success="
    And I should see "Imported 2 contacts, skipped 1"
    And the contacts should have been imported

  Scenario: A file that is not a CSV is refused
    Given the mailler service imports contacts
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/import"
    And I choose the file "people.txt" for "CSV File *" with the following content
      """
      email
      ada@example.com
      """
    And I click "Import Contacts"
    Then the URL should contain "/contacts/import?error="
    And I should see "Please upload a CSV file"

  Scenario: A CSV without any valid contact is refused
    Given the mailler service imports contacts
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts/import"
    And I choose the file "empty.csv" for "CSV File *" with the following content
      """
      email,first_name
      ,Nobody
      """
    And I click "Import Contacts"
    Then I should see "No valid contacts found in CSV"

  Scenario: The contacts are exported as a CSV file
    Given the contacts list returns data for export
    And I sign in with the scopes "contacts:*"
    When I navigate to "/contacts"
    And I download the file with "Export CSV"
    Then the downloaded file should be called "contacts.csv"
    And the downloaded file should contain "email,first_name,last_name,status,source"
    And the downloaded file should contain "test@example.com"
