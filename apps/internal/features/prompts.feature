Feature: System prompt management with versioning
  As an admin user with prompt permissions
  I want to manage system prompts and their versions
  So that I can configure AI assistant behavior

  Background:
    Given I am a super admin

  # --- List ---

  Scenario: List prompts
    When I send a GET request to "/prompts"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: List prompts with search filter
    Given a prompt "custom" with name "Custom Prompt" exists
    When I send a GET request to "/prompts?search=Custom"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: List prompts unauthenticated
    Given I am not authenticated
    When I send a GET request to "/prompts"
    Then the response status code should be 302

  # --- New form ---

  Scenario: View new prompt form
    When I send a GET request to "/prompts/new"
    Then the response status code should be 200
    And the response should be HTML

  # --- Create ---

  Scenario: Create a prompt
    When I send a POST request to "/prompts/new" with form data
      | field           | value                     |
      | slug            | test-prompt               |
      | name            | Test Prompt               |
      | content         | You are a test assistant.  |
      | description     | A test prompt             |
      | required_scopes |                           |
      | is_default      | false                     |
      | metadata_json   | {}                        |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Prompt+created"

  Scenario: Create a prompt with duplicate slug
    Given a prompt "duplicate" with name "Duplicate" exists
    When I send a POST request to "/prompts/new" with form data
      | field           | value                     |
      | slug            | duplicate                 |
      | name            | Duplicate Again           |
      | content         | Some content              |
      | description     |                           |
      | required_scopes |                           |
      | is_default      | false                     |
      | metadata_json   | {}                        |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Prompt+with+slug"

  Scenario: Create a prompt with invalid metadata JSON
    When I send a POST request to "/prompts/new" with form data
      | field           | value                     |
      | slug            | bad-meta                  |
      | name            | Bad Meta                  |
      | content         | Some content              |
      | description     |                           |
      | required_scopes |                           |
      | is_default      | false                     |
      | metadata_json   | {invalid}                 |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Invalid+JSON"

  # --- Generate ---

  Scenario: View generate prompt form when OpenAI configured
    Given OpenAI is configured
    When I send a GET request to "/prompts/generate"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View generate prompt form when OpenAI not configured
    Given OpenAI is not configured
    When I send a GET request to "/prompts/generate"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=OpenAI+not+configured"

  Scenario: Generate a prompt via AI
    Given OpenAI is configured
    And the prompt generator returns data
    When I send a POST request to "/prompts/generate" with form data
      | field           | value                                          |
      | description     | A helpful customer support assistant prompt     |
      | tone            | professional                                   |
      | focus_areas     | customer service                               |
      | constraints     | be polite                                      |
      | required_scopes |                                                |
      | is_default      | false                                          |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/prompts/new?generated=1"

  Scenario: Generate a prompt with short description
    Given OpenAI is configured
    When I send a POST request to "/prompts/generate" with form data
      | field           | value     |
      | description     | too short |
      | tone            | casual    |
      | focus_areas     |           |
      | constraints     |           |
      | required_scopes |           |
      | is_default      | false     |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Description+too+short"

  # --- Detail ---

  Scenario: View prompt detail
    Given a prompt "detail-test" with name "Detail Test" exists
    When I view the prompt detail
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View prompt detail not found
    When I send a GET request to "/prompts/99999"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Prompt+not+found"

  # --- Edit ---

  Scenario: View prompt edit form
    Given a prompt "edit-test" with name "Edit Test" exists
    When I view the prompt edit form
    Then the response status code should be 200
    And the response should be HTML

  Scenario: Update a prompt
    Given a prompt "to-update" with name "To Update" exists
    When I update the prompt with form data
      | field           | value                        |
      | slug            | to-update                    |
      | name            | Updated Prompt               |
      | content         | Updated content for prompt.  |
      | description     | Updated description          |
      | required_scopes |                              |
      | is_default      | false                        |
      | metadata_json   | {}                           |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Prompt+updated"

  # --- Version management ---

  Scenario: Activate a prompt version
    Given a prompt "versioned" with name "Versioned" and multiple versions exists
    When I activate the old prompt version
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Version"

  Scenario: Delete a non-current prompt version
    Given a prompt "ver-delete" with name "Version Delete" and multiple versions exists
    When I delete the old prompt version
    Then the response status code should be 303
    And I should be redirected to a URL containing "deleted"

  Scenario: Cannot delete current prompt version
    Given a prompt "ver-current" with name "Version Current" exists
    When I delete the current prompt version
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Cannot+delete+the+current+version"

  # --- Delete prompt ---

  Scenario: Delete a prompt
    Given a prompt "to-delete" with name "To Delete" exists
    When I delete the prompt
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Prompt+deleted"

  Scenario: Cannot delete the default prompt
    Given a default prompt exists
    When I delete the prompt
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Cannot+delete+the+default+prompt"

  # --- Bulk delete ---

  Scenario: Bulk delete prompts
    Given a prompt "bulk-1" with name "Bulk 1" exists
    And another prompt "bulk-2" with name "Bulk 2" exists
    When I bulk delete the created prompts
    Then the response status code should be 303
    And I should be redirected to a URL containing "prompt(s)+deleted+successfully"

  Scenario: Bulk delete versions
    Given a prompt "bulk-ver" with name "Bulk Versions" and multiple versions exists
    When I bulk delete the non-current prompt versions
    Then the response status code should be 303
    And I should be redirected to a URL containing "version(s)+deleted"

  # --- Sidebar ---

  Scenario: Sidebar on the prompts list
    Given I am authenticated with only the scopes "prompts:* vpn:admin billing:read" granted by token exchange
    When I send a GET request to "/prompts"
    Then the response status code should be 200
    And the active sidebar link should be "/prompts"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the new prompt form
    Given I am authenticated with only the scopes "prompts:* vpn:admin billing:read" granted by token exchange
    When I send a GET request to "/prompts/new"
    Then the response status code should be 200
    And the active sidebar link should be "/prompts"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the generate prompt form
    Given I am authenticated with only the scopes "prompts:* vpn:admin billing:read" granted by token exchange
    And OpenAI is configured
    When I send a GET request to "/prompts/generate"
    Then the response status code should be 200
    And the active sidebar link should be "/prompts"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the prompt detail
    Given I am authenticated with only the scopes "prompts:* vpn:admin billing:read" granted by token exchange
    And a prompt "support" with name "Support" exists
    When I view the prompt detail
    Then the response status code should be 200
    And the active sidebar link should be "/prompts"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the prompt edit form
    Given I am authenticated with only the scopes "prompts:* vpn:admin billing:read" granted by token exchange
    And a prompt "support" with name "Support" exists
    When I view the prompt edit form
    Then the response status code should be 200
    And the active sidebar link should be "/prompts"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario Outline: Sidebar gated links follow the scopes on the prompts list
    Given I am authenticated with only the scopes "<scopes>" granted by token exchange
    When I send a GET request to "/prompts"
    Then the response status code should be 200
    And the sidebar link to "/vpn/sessions" should be <vpn>
    And the sidebar link to "/billing" should be <billing>

    Examples:
      | scopes                           | vpn     | billing |
      | prompts:*                        | hidden  | hidden  |
      | prompts:* vpn:admin              | visible | hidden  |
      | prompts:* billing:read           | hidden  | visible |
      | prompts:* vpn:admin billing:read | visible | visible |
      | *                                | visible | visible |
