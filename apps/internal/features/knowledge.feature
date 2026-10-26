Feature: Knowledge base entry management
  As an admin user with knowledge permissions
  I want to manage knowledge base entries
  So that I can maintain the RAG knowledge base

  Background:
    Given I am a super admin

  # --- List ---

  Scenario: List knowledge entries when empty
    When I send a GET request to "/knowledge"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: List knowledge entries with data
    Given a namespace "general" with name "General" exists
    And a knowledge entry exists with question "What is Python?" and answer "A programming language"
    When I send a GET request to "/knowledge"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: List knowledge entries with search filter
    Given a namespace "general" with name "General" exists
    And a knowledge entry exists with question "What is Python?" and answer "A programming language"
    When I send a GET request to "/knowledge?search=Python"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: List knowledge entries filtered by namespace
    Given a namespace "general" with name "General" exists
    And a knowledge entry exists with question "General question" and answer "General answer"
    When I send a GET request to "/knowledge?namespace=general"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: List knowledge entries unauthenticated
    Given I am not authenticated
    When I send a GET request to "/knowledge"
    Then the response status code should be 302

  # --- New form ---

  Scenario: View new knowledge entry form
    When I send a GET request to "/knowledge/new"
    Then the response status code should be 200
    And the response should be HTML

  # --- Create ---

  Scenario: Create a knowledge entry
    Given a namespace "general" with name "General" exists
    When I create a knowledge entry with form data
      | field          | value                    |
      | question       | What is Ansible?         |
      | answer         | An automation tool       |
      | namespace_id   | {namespace_id}           |
      | metadata_json  | {}                       |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Knowledge+entry+created"

  Scenario: Create a knowledge entry with invalid metadata JSON
    Given a namespace "general" with name "General" exists
    When I create a knowledge entry with form data
      | field          | value                    |
      | question       | Test question            |
      | answer         | Test answer              |
      | namespace_id   | {namespace_id}           |
      | metadata_json  | {invalid json}           |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Invalid+JSON"

  # --- Generate ---

  Scenario: View generate knowledge form when OpenAI configured
    Given OpenAI is configured
    When I send a GET request to "/knowledge/generate"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View generate knowledge form when OpenAI not configured
    Given OpenAI is not configured
    When I send a GET request to "/knowledge/generate"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=OpenAI+not+configured"

  Scenario: Generate knowledge entries dispatches async task
    Given a namespace "general" with name "General" exists
    And OpenAI is configured
    When I generate knowledge entries with form data
      | field          | value                                                          |
      | source_text    | This is a sufficiently long source text for generating knowledge entries from the AI service |
      | namespace_id   | {namespace_id}                                                 |
      | num_entries    | 2                                                              |
      | context        | test context                                                   |
    Then the response status code should be 200
    And the response should be valid JSON
    And the response JSON should have key "task_id"

  Scenario: Poll generation task status returns SUCCESS
    Given I am a super admin
    And the generation task completed successfully
    When I send a GET request to "/knowledge/generate/status/test-task-123"
    Then the response status code should be 200
    And the response should be valid JSON
    And the response JSON key "state" should equal "SUCCESS"

  # --- Detail ---

  Scenario: View knowledge entry detail
    Given a namespace "general" with name "General" exists
    And a knowledge entry exists with question "What is Docker?" and answer "A container platform"
    When I view the knowledge entry detail
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View knowledge entry detail not found
    When I send a GET request to "/knowledge/99999"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Knowledge+entry+not+found"

  # --- Edit ---

  Scenario: View knowledge entry edit form
    Given a namespace "general" with name "General" exists
    And a knowledge entry exists with question "Old question" and answer "Old answer"
    When I view the knowledge entry edit form
    Then the response status code should be 200
    And the response should be HTML

  Scenario: Update a knowledge entry
    Given a namespace "general" with name "General" exists
    And a knowledge entry exists with question "Old question" and answer "Old answer"
    When I update the knowledge entry with form data
      | field          | value                    |
      | question       | Updated question         |
      | answer         | Updated answer           |
      | namespace_id   | {namespace_id}           |
      | metadata_json  | {}                       |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Knowledge+entry+updated"

  # --- Delete ---

  Scenario: Delete a knowledge entry
    Given a namespace "general" with name "General" exists
    And a knowledge entry exists with question "To delete" and answer "Will be removed"
    When I delete the knowledge entry
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Knowledge+entry+deleted"

  # --- Bulk delete ---

  Scenario: Bulk delete knowledge entries
    Given a namespace "general" with name "General" exists
    And a knowledge entry exists with question "Bulk 1" and answer "Answer 1"
    And another knowledge entry exists with question "Bulk 2" and answer "Answer 2"
    When I bulk delete the created knowledge entries
    Then the response status code should be 303
    And I should be redirected to a URL containing "entry(ies)+deleted+successfully"

  Scenario: Bulk delete with empty list
    When I send a POST request to "/knowledge/bulk-delete" with form data
      | field     | value |
      | entry_ids |       |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=No+entries+selected"
