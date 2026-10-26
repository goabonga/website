Feature: Contacts management with CSV import and export
  As an admin user with contacts permissions
  I want to manage contacts, import from CSV, and export to CSV
  So that I can maintain the contact database via Mailler API

  Background:
    Given I am a super admin

  # ==========================================================================
  # List
  # ==========================================================================

  @contacts
  Scenario: View contacts list
    Given the contacts list returns data
    When I send a GET request to "/contacts"
    Then the response status code should be 200
    And the response should be HTML

  @contacts
  Scenario: View contacts list unauthenticated
    Given I am not authenticated
    When I send a GET request to "/contacts"
    Then the response status code should be 302

  @contacts
  Scenario: View contacts list with search filter
    Given the contacts list returns data
    When I send a GET request to "/contacts?search=john"
    Then the response status code should be 200
    And the response should be HTML

  @contacts
  Scenario: View contacts list with status filter
    Given the contacts list returns data
    When I send a GET request to "/contacts?status=active"
    Then the response status code should be 200
    And the response should be HTML

  # ==========================================================================
  # Create
  # ==========================================================================

  @contacts
  Scenario: View new contact form
    Given the contact groups list returns data
    When I send a GET request to "/contacts/new"
    Then the response status code should be 200
    And the response should be HTML

  @contacts
  Scenario: Create a new contact successfully
    Given creating a contact succeeds
    When I send a POST request to "/contacts/new" with form data
      | field      | value              |
      | email      | john@example.com   |
      | first_name | John               |
      | last_name  | Doe                |
      | status     | active             |
      | source     | manual             |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/contacts"
    And I should be redirected to a URL containing "success=Contact+created"

  @contacts
  Scenario: Create a new contact failure
    Given creating a contact fails
    When I send a POST request to "/contacts/new" with form data
      | field | value            |
      | email | fail@example.com |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+create"

  # ==========================================================================
  # Import / Export
  # ==========================================================================

  @contacts
  Scenario: View import form
    When I send a GET request to "/contacts/import"
    Then the response status code should be 200
    And the response should be HTML

  @contacts
  Scenario: Export contacts as CSV
    Given the contacts list returns data for export
    When I send a GET request to "/contacts/export"
    Then the response status code should be 200

  # ==========================================================================
  # Detail
  # ==========================================================================

  @contacts
  Scenario: View contact detail
    Given a contact exists with id "42"
    When I send a GET request to "/contacts/42"
    Then the response status code should be 200
    And the response should be HTML

  @contacts
  Scenario: View contact detail not found
    Given a contact does not exist
    When I send a GET request to "/contacts/999"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Contact+not+found"

  # ==========================================================================
  # Edit
  # ==========================================================================

  @contacts
  Scenario: View contact edit form
    Given a contact exists with id "42"
    And the contact groups list returns data
    When I send a GET request to "/contacts/42/edit"
    Then the response status code should be 200
    And the response should be HTML

  @contacts
  Scenario: View contact edit form not found
    Given a contact does not exist
    When I send a GET request to "/contacts/999/edit"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Contact+not+found"

  @contacts
  Scenario: Update a contact successfully
    Given updating a contact succeeds for id "42"
    When I send a POST request to "/contacts/42/edit" with form data
      | field      | value      |
      | first_name | Jane       |
      | last_name  | Doe        |
      | status     | active     |
      | source     | manual     |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/contacts/42"
    And I should be redirected to a URL containing "success=Contact+updated"

  @contacts
  Scenario: Update a contact failure
    Given updating a contact fails for id "42"
    When I send a POST request to "/contacts/42/edit" with form data
      | field      | value |
      | first_name | Jane  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+update"

  # ==========================================================================
  # Unsubscribe
  # ==========================================================================

  @contacts
  Scenario: Unsubscribe a contact successfully
    Given unsubscribing a contact succeeds for id "42"
    When I send a POST request to "/contacts/42/unsubscribe"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Contact+marked+as+unsubscribed"

  @contacts
  Scenario: Unsubscribe a contact failure
    Given unsubscribing a contact fails for id "42"
    When I send a POST request to "/contacts/42/unsubscribe"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Contact+not+found"

  # ==========================================================================
  # Delete
  # ==========================================================================

  @contacts
  Scenario: Delete a contact successfully
    Given deleting a contact succeeds for id "42"
    When I send a POST request to "/contacts/42/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Contact+deleted"

  @contacts
  Scenario: Delete a contact failure
    Given deleting a contact fails for id "42"
    When I send a POST request to "/contacts/42/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+delete"

  # ==========================================================================
  # Bulk operations
  # ==========================================================================

  @contacts
  Scenario: Bulk delete contacts
    Given bulk deleting contacts succeeds
    When I send a POST request to "/contacts/bulk-delete" with form data
      | field       | value |
      | contact_ids | 1,2,3 |
    Then the response status code should be 303
    And I should be redirected to a URL containing "contact(s)+deleted"

  @contacts
  Scenario: Bulk delete with no contacts selected
    When I send a POST request to "/contacts/bulk-delete" with form data
      | field       | value |
      | contact_ids |       |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=No+contacts+selected"

  @contacts
  Scenario: Bulk add contacts to group
    Given bulk adding contacts to group succeeds
    When I send a POST request to "/contacts/bulk-add-to-group" with form data
      | field       | value |
      | contact_ids | 1,2,3 |
      | group_id    | 10    |
    Then the response status code should be 303
    And I should be redirected to a URL containing "contact(s)+added+to+group"
