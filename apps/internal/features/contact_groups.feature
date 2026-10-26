Feature: Contact groups management
  As an admin user with contacts permissions
  I want to manage contact groups, add and remove members
  So that I can organize contacts into logical groups via Mailler API

  Background:
    Given I am a super admin

  # ==========================================================================
  # List
  # ==========================================================================

  @contact-groups
  Scenario: View contact groups list
    Given the contact groups list returns groups
    When I send a GET request to "/contact-groups"
    Then the response status code should be 200
    And the response should be HTML

  @contact-groups
  Scenario: View contact groups list unauthenticated
    Given I am not authenticated
    When I send a GET request to "/contact-groups"
    Then the response status code should be 302

  @contact-groups
  Scenario: View contact groups list with search
    Given the contact groups list returns groups
    When I send a GET request to "/contact-groups?search=newsletter"
    Then the response status code should be 200
    And the response should be HTML

  # ==========================================================================
  # Create
  # ==========================================================================

  @contact-groups
  Scenario: View new group form
    When I send a GET request to "/contact-groups/new"
    Then the response status code should be 200
    And the response should be HTML

  @contact-groups
  Scenario: Create a contact group successfully
    Given creating a contact group succeeds
    When I send a POST request to "/contact-groups/new" with form data
      | field       | value                    |
      | name        | VIP Customers            |
      | slug        | vip-customers            |
      | description | High-value customers     |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/contact-groups"
    And I should be redirected to a URL containing "success=Group+created"

  @contact-groups
  Scenario: Create a contact group failure
    Given creating a contact group fails
    When I send a POST request to "/contact-groups/new" with form data
      | field | value     |
      | name  | Bad Group |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+create"

  # ==========================================================================
  # Detail
  # ==========================================================================

  @contact-groups
  Scenario: View group detail
    Given a contact group exists with id "1"
    When I send a GET request to "/contact-groups/1"
    Then the response status code should be 200
    And the response should be HTML

  @contact-groups
  Scenario: View group detail not found
    Given a contact group does not exist
    When I send a GET request to "/contact-groups/999"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Group+not+found"

  # ==========================================================================
  # Edit
  # ==========================================================================

  @contact-groups
  Scenario: View group edit form
    Given a contact group exists with id "1"
    When I send a GET request to "/contact-groups/1/edit"
    Then the response status code should be 200
    And the response should be HTML

  @contact-groups
  Scenario: View group edit form not found
    Given a contact group does not exist
    When I send a GET request to "/contact-groups/999/edit"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Group+not+found"

  @contact-groups
  Scenario: Update a contact group successfully
    Given updating a contact group succeeds for id "1"
    When I send a POST request to "/contact-groups/1/edit" with form data
      | field       | value            |
      | name        | Updated Group    |
      | slug        | updated-group    |
      | description | Updated desc     |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/contact-groups/1"
    And I should be redirected to a URL containing "success=Group+updated"

  @contact-groups
  Scenario: Update a contact group failure
    Given updating a contact group fails for id "1"
    When I send a POST request to "/contact-groups/1/edit" with form data
      | field | value         |
      | name  | Updated Group |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+update"

  # ==========================================================================
  # Add contacts
  # ==========================================================================

  @contact-groups
  Scenario: View add contacts form
    Given a contact group exists with id "1"
    And contacts not in group "1" returns data
    When I send a GET request to "/contact-groups/1/add-contacts"
    Then the response status code should be 200
    And the response should be HTML

  @contact-groups
  Scenario: Add contacts to a group successfully
    Given adding contacts to group "1" succeeds
    When I send a POST request to "/contact-groups/1/add-contacts" with form data
      | field       | value |
      | contact_ids | 1,2,3 |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/contact-groups/1"
    And I should be redirected to a URL containing "contact(s)+added"

  @contact-groups
  Scenario: Add contacts with none selected
    When I send a POST request to "/contact-groups/1/add-contacts" with form data
      | field       | value |
      | contact_ids |       |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=No+contacts+selected"

  # ==========================================================================
  # Remove contacts
  # ==========================================================================

  @contact-groups
  Scenario: Remove contacts from a group
    Given removing contacts from group "1" succeeds
    When I send a POST request to "/contact-groups/1/remove-contacts" with form data
      | field       | value |
      | contact_ids | 1,2   |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/contact-groups/1"
    And I should be redirected to a URL containing "contact(s)+removed"

  @contact-groups
  Scenario: Remove contacts with none selected
    When I send a POST request to "/contact-groups/1/remove-contacts" with form data
      | field       | value |
      | contact_ids |       |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=No+contacts+selected"

  # ==========================================================================
  # Delete
  # ==========================================================================

  @contact-groups
  Scenario: Delete a contact group successfully
    Given a contact group exists with id "1"
    And deleting contact group "1" succeeds
    When I send a POST request to "/contact-groups/1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Group+deleted"

  @contact-groups
  Scenario: Delete a contact group not found
    Given a contact group does not exist
    When I send a POST request to "/contact-groups/999/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Group+not+found"

  @contact-groups
  Scenario: Bulk delete contact groups
    Given bulk deleting contact groups succeeds
    When I send a POST request to "/contact-groups/bulk-delete" with form data
      | field     | value |
      | group_ids | 1     |
      | group_ids | 2     |
    Then the response status code should be 303
    And I should be redirected to a URL containing "group(s)+deleted"
