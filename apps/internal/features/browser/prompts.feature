@browser
Feature: System prompts in a browser
  As an operator with the prompt permissions
  I want to manage the system prompts and their versions
  So that the assistant answers with the right instructions

  # --- Access and sidebar ---

  Scenario: The prompts are listed with their current version
    Given a prompt "pro" with name "Pro prompt" and multiple versions exists
    And I sign in with the scopes "prompts:*"
    When I navigate to "/prompts"
    Then the page title should be "System Prompts - Internal Admin"
    And I should see "Pro prompt"
    And I should see "v2"
    And the sidebar menu should highlight only "Prompts"
    And the browser should report no errors

  Scenario: The Prompts link leads to the list
    Given I sign in with the scopes "prompts:*"
    When I navigate to "/prompts/new"
    Then the sidebar menu should highlight only "Prompts"
    When I follow the sidebar link "Prompts"
    Then the URL should be "/prompts"

  Scenario: A user without the prompt scope gets the access denied page
    Given I sign in with the scopes "contacts:read"
    When I navigate to "/prompts"
    Then the page title should contain "Access Denied"
    And I should see "prompts:read"

  Scenario: An anonymous visitor comes back to the page asked for after the login
    Given a user holding the scopes "prompts:*" exists at the provider
    And a prompt "pro" with name "Pro prompt" and multiple versions exists
    When I navigate to "/prompts?search=pro"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/prompts?search=pro"
    And I should see "Pro prompt"

  Scenario: Searching narrows the list
    Given a prompt "alpha" with name "Alpha" exists
    And another prompt "beta" with name "Beta" exists
    And I sign in with the scopes "prompts:*"
    When I navigate to "/prompts"
    And I fill "search" with "alph"
    And I click "Search"
    Then the URL should contain "search=alph"
    And I should see "Alpha"
    And I should not see "Beta"

  Scenario: The list is paginated and keeps the search
    Given 25 prompts named "Team & Co" exist
    And a prompt "other" with name "Team other" exists
    And I sign in with the scopes "prompts:*"
    When I navigate to "/prompts"
    And I fill "search" with "Team & Co"
    And I click "Search"
    Then I should see "Showing 20 of 25 prompts"
    When I click "Next"
    Then I should see "Showing 5 of 25 prompts"
    And I should see "Team & Co 024"

  # --- Creating and editing ---

  Scenario: A prompt is created from the form
    Given I sign in with the scopes "prompts:*"
    When I navigate to "/prompts"
    And I click "New Prompt"
    Then the URL should be "/prompts/new"
    When I fill "Slug *" with "support"
    And I fill "Name *" with "Support prompt"
    And I fill "Prompt Content *" with "You are a helpful support assistant."
    And I click "Create Prompt"
    Then the URL should contain "/prompts?success="
    And I should see "Prompt created successfully"
    And I should see "Support prompt"

  Scenario: A slug already in use is reported on the form
    Given a prompt "duplicate" with name "Duplicate" exists
    And I sign in with the scopes "prompts:*"
    When I navigate to "/prompts/new"
    And I fill "Slug *" with "duplicate"
    And I fill "Name *" with "Duplicate again"
    And I fill "Prompt Content *" with "Content"
    And I click "Create Prompt"
    Then the URL should contain "/prompts/new?error="
    And I should see "Prompt with slug 'duplicate' already exists"

  Scenario: Metadata that is not JSON is reported on the form
    Given I sign in with the scopes "prompts:*"
    When I navigate to "/prompts/new"
    And I fill "Slug *" with "support"
    And I fill "Name *" with "Support prompt"
    And I fill "Prompt Content *" with "Content"
    And I fill "Metadata (JSON)" with "{not json"
    And I click "Create Prompt"
    Then I should see "Invalid JSON in metadata field"

  Scenario: The character count follows the content
    Given I sign in with the scopes "prompts:*"
    When I navigate to "/prompts/new"
    And I fill "Prompt Content *" with "12345"
    Then I should see "5 characters"

  Scenario: A prompt is updated and gets a new version
    Given a prompt "pro" with name "Pro prompt" and multiple versions exists
    And I sign in with the scopes "prompts:*"
    When I open the prompt I created
    And I click "Edit Prompt"
    Then the URL should contain "/edit"
    And the field "Name *" should contain "Pro prompt"
    When I fill "Name *" with "Pro prompt v3"
    And I fill "Prompt Content *" with "Brand new content"
    And I click "Save Changes"
    Then the URL should contain "?success="
    And I should see "Prompt updated successfully"
    And I should see "Pro prompt v3"

  Scenario: A prompt that does not exist sends the user back to the list
    Given I sign in with the scopes "prompts:*"
    When I navigate to "/prompts/99999"
    Then the URL should contain "/prompts?error="
    And I should see "Prompt not found"

  # --- Versions ---

  Scenario: The detail of a prompt shows its versions
    Given a prompt "pro" with name "Pro prompt" and multiple versions exists
    And I sign in with the scopes "prompts:*"
    When I open the prompt I created
    Then I should see "VERSION HISTORY"
    And I should see "Version 2 content for Pro prompt"
    And I should see "Version 1 content for Pro prompt"

  Scenario: An old version is activated after a confirmation
    Given a prompt "pro" with name "Pro prompt" and multiple versions exists
    And I sign in with the scopes "prompts:*"
    When I open the prompt I created
    And I click "Activate"
    Then the page should have asked for a confirmation containing "Activate version 1?"
    And I should see "Version 1 activated"

  Scenario: An old version is deleted after a confirmation
    Given a prompt "pro" with name "Pro prompt" and multiple versions exists
    And I sign in with the scopes "prompts:*"
    When I open the prompt I created
    And I click "css=button:has-text('Delete'):not(:has-text('Selected')):not(:has-text('Prompt'))"
    Then the page should have asked for a confirmation containing "Delete version 1?"
    And I should see "Version 1 deleted"

  Scenario: Selected versions are deleted in bulk
    Given a prompt "pro" with name "Pro prompt" and multiple versions exists
    And I sign in with the scopes "prompts:*"
    When I open the prompt I created
    And I click "Select all"
    And I click "Delete Selected"
    Then the page should have asked for a confirmation containing "delete"
    And I should see "1 version(s) deleted successfully"

  # --- Deleting ---

  Scenario: A prompt is deleted from its page after a confirmation
    Given a prompt "to-delete" with name "To Delete" exists
    And I sign in with the scopes "prompts:*"
    When I open the prompt I created
    And I click "Delete Prompt"
    Then the page should have asked for a confirmation containing "delete this prompt"
    And the URL should contain "/prompts?success="
    And I should see "Prompt deleted successfully"
    And I should not see "To Delete"

  Scenario: A prompt is deleted from its edit form after a confirmation
    Given a prompt "to-delete" with name "To Delete" exists
    And I sign in with the scopes "prompts:*"
    When I open the edit form of the prompt I created
    And I click "Delete" in the page content
    Then the page should have asked for a confirmation containing "delete this prompt"
    And the URL should contain "/prompts?success="
    And I should see "Prompt deleted successfully"
    And I should not see "To Delete"

  Scenario: Dismissing the confirmation keeps the prompt
    Given a prompt "to-keep" with name "To Keep" exists
    And I sign in with the scopes "prompts:*"
    When I open the edit form of the prompt I created
    And I dismiss the next confirmation
    And I click "Delete" in the page content
    Then the URL should contain "/edit"
    When I navigate to "/prompts"
    Then I should see "To Keep"

  Scenario: The default prompt cannot be deleted
    Given a default prompt exists
    And I sign in with the scopes "prompts:*"
    When I open the prompt I created
    Then "Delete Prompt" should be hidden

  Scenario: Selected prompts are deleted in bulk
    Given a prompt "bulk-1" with name "Bulk 1" exists
    And another prompt "bulk-2" with name "Bulk 2" exists
    And I sign in with the scopes "prompts:*"
    When I navigate to "/prompts"
    And I click "css=#selectAll"
    And I click "Delete Selected"
    Then the page should have asked for a confirmation containing "delete"
    And I should see "2 prompt(s) deleted, 1 skipped (default)"

  # --- Generating ---

  Scenario: The generate page needs OpenAI
    Given OpenAI is not configured
    And I sign in with the scopes "prompts:*"
    When I navigate to "/prompts/generate"
    Then the URL should contain "/prompts?error="
    And I should see "OpenAI not configured"

  Scenario: A prompt is generated and opened in the form for review
    Given OpenAI is configured
    And the prompt generator returns data
    And I sign in with the scopes "prompts:*"
    When I navigate to "/prompts"
    And I click "Generate"
    Then the URL should be "/prompts/generate"
    When I fill "Description *" with "A helpful customer support assistant prompt"
    And I click "Generate Prompt"
    Then the URL should contain "/prompts/new?generated=1"
    And the field "Name *" should contain "Generated Prompt"
    And the field "Slug *" should contain "generated-prompt"
    And the field "Prompt Content *" should contain "customer support assistant"

  Scenario: A description that is too short is stopped by the form
    Given OpenAI is configured
    And the prompt generator returns data
    And I sign in with the scopes "prompts:*"
    When I navigate to "/prompts/generate"
    And I fill "Description *" with "too short"
    And I click "Generate Prompt"
    Then the URL should be "/prompts/generate"
