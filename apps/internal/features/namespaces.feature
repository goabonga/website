Feature: Knowledge namespace management
  As an admin user with namespace permissions
  I want to manage knowledge namespaces
  So that I can organize knowledge base entries into categories

  Background:
    Given I am a super admin

  # --- List ---

  Scenario: List namespaces
    When I send a GET request to "/namespaces"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: List namespaces with search filter
    Given a namespace "testing" with name "Testing" exists for namespaces
    When I send a GET request to "/namespaces?search=Testing"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: List namespaces unauthenticated
    Given I am not authenticated
    When I send a GET request to "/namespaces"
    Then the response status code should be 302

  # --- New form ---

  Scenario: View new namespace form
    When I send a GET request to "/namespaces/new"
    Then the response status code should be 200
    And the response should be HTML

  # --- Create ---

  Scenario: Create a namespace
    When I send a POST request to "/namespaces/new" with form data
      | field           | value               |
      | slug            | my-namespace        |
      | name            | My Namespace        |
      | description     | A test namespace    |
      | required_scopes |                     |
      | is_public       | true                |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Namespace+created"

  Scenario: Create a namespace with duplicate slug
    Given a namespace "duplicate" with name "Duplicate" exists for namespaces
    When I send a POST request to "/namespaces/new" with form data
      | field           | value               |
      | slug            | duplicate           |
      | name            | Duplicate Again     |
      | description     |                     |
      | required_scopes |                     |
      | is_public       | true                |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Namespace+with+slug"

  # --- Detail ---

  Scenario: View namespace detail
    Given a namespace "detail-test" with name "Detail Test" exists for namespaces
    When I view the namespace detail
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View namespace detail not found
    When I send a GET request to "/namespaces/99999"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Namespace+not+found"

  # --- Edit ---

  Scenario: View namespace edit form
    Given a namespace "edit-test" with name "Edit Test" exists for namespaces
    When I view the namespace edit form
    Then the response status code should be 200
    And the response should be HTML

  Scenario: Update a namespace
    Given a namespace "to-update" with name "To Update" exists for namespaces
    When I update the namespace with form data
      | field           | value               |
      | slug            | to-update           |
      | name            | Updated Namespace   |
      | description     | Updated description |
      | required_scopes |                     |
      | is_public       | true                |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Namespace+updated"

  # --- Delete ---

  Scenario: Delete a namespace
    Given a namespace "to-delete" with name "To Delete" exists for namespaces
    When I delete the namespace
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Namespace+deleted"

  Scenario: Cannot delete the default general namespace
    Given the default general namespace exists
    When I delete the namespace
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Cannot+delete+the+default+namespace"

  # --- Bulk delete ---

  Scenario: Bulk delete namespaces
    Given a namespace "bulk-1" with name "Bulk 1" exists for namespaces
    And another namespace "bulk-2" with name "Bulk 2" exists for namespaces
    When I bulk delete the created namespaces
    Then the response status code should be 303
    And I should be redirected to a URL containing "namespace(s)+deleted+successfully"
