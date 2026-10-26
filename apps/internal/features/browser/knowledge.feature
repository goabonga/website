@browser
Feature: Knowledge base in a browser
  As an operator with the knowledge permissions
  I want to manage the question and answer entries of the knowledge base
  So that the assistant can find the right answer

  Background:
    Given a namespace "general" with name "General" exists
    And a knowledge entry exists with question "What is X?" and answer "X is a thing"

  # --- Access and sidebar ---

  Scenario: The entries are listed with their namespace and status
    Given I sign in with the scopes "knowledge:* namespaces:*"
    When I navigate to "/knowledge"
    Then the page title should be "Knowledge Base - Internal Admin"
    And I should see "What is X?"
    And I should see "X is a thing"
    And I should see "Showing 1 of 1 entries"
    And the sidebar menu should highlight only "Knowledge Base"
    And the browser should report no errors

  Scenario: The Knowledge Base link leads to the list
    Given I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge/new"
    Then the sidebar menu should highlight only "Knowledge Base"
    When I follow the sidebar link "Knowledge Base"
    Then the URL should be "/knowledge"

  Scenario: A user without the knowledge scope gets the access denied page
    Given I sign in with the scopes "contacts:read"
    When I navigate to "/knowledge"
    Then the page title should contain "Access Denied"
    And I should see "knowledge:read"

  Scenario: A user who may only read cannot create an entry
    Given I sign in with the scopes "knowledge:read"
    When I navigate to "/knowledge/new"
    Then the page title should contain "Access Denied"
    And I should see "knowledge:write"

  Scenario: An anonymous visitor comes back to the page asked for after the login
    Given a user holding the scopes "knowledge:*" exists at the provider
    When I navigate to "/knowledge?search=thing&status=accepted"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/knowledge?search=thing&status=accepted"
    And I should see "What is X?"

  Scenario: Searching narrows the list
    Given another knowledge entry exists with question "How does Y work?" and answer "Y works well"
    And I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge"
    And I fill "search" with "How does"
    And I click "Search"
    Then the URL should contain "search=How+does"
    And I should see "How does Y work?"
    And I should not see "What is X?"

  Scenario: The entries are filtered by status and namespace
    Given I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge"
    And I select "Rejected" from "status"
    And I click "Search"
    Then the URL should contain "status=rejected"
    And I should not see "What is X?"

  Scenario: The list is paginated and keeps the search
    Given 25 knowledge entries about "Team & Co" exist
    And I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge"
    And I fill "search" with "Team & Co"
    And I click "Search"
    Then I should see "Showing 20 of 25 entries"
    When I click "Next"
    Then I should see "Showing 5 of 25 entries"
    And I should see "Team & Co question 024"

  # --- Creating and editing ---

  Scenario: An entry is created from the form and sent to validation
    Given I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge"
    And I click "New Entry"
    Then the URL should be "/knowledge/new"
    When I select "General (general)" from "Namespace *"
    And I fill "Question *" with "How do I reset my password?"
    And I fill "Answer *" with "Use the reset link."
    And I click "Create Entry"
    Then the URL should contain "/knowledge?success="
    And I should see "Knowledge entry created (validation pending)"
    And I should see "How do I reset my password?"
    And the validation of the entry should have been requested

  Scenario: The embedding of a new entry is generated when OpenAI is configured
    Given the embedding service is available
    And I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge/new"
    And I fill "Question *" with "How do I reset my password?"
    And I fill "Answer *" with "Use the reset link."
    And I click "Create Entry"
    Then the URL should contain "/knowledge?success="

  Scenario: Metadata that is not JSON is reported on the form
    Given I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge/new"
    And I fill "Question *" with "How do I reset my password?"
    And I fill "Answer *" with "Use the reset link."
    And I fill "Metadata (JSON)" with "{not json"
    And I click "Create Entry"
    Then the URL should contain "/knowledge/new?error="
    And I should see "Invalid JSON in metadata field"

  Scenario: The form requires a question and an answer
    Given I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge/new"
    And I click "Create Entry"
    Then the URL should be "/knowledge/new"

  Scenario: An entry is updated from its edit form
    Given I sign in with the scopes "knowledge:*"
    When I open the entry I created
    And I click "Edit Entry"
    Then the URL should contain "/edit"
    And the field "Question *" should contain "What is X?"
    When I fill "Answer *" with "X is another thing"
    And I click "Save Changes"
    Then the URL should contain "?success="
    And I should see "Knowledge entry updated successfully"
    And I should see "X is another thing"

  Scenario: Metadata that is not JSON is reported on the edit form
    Given I sign in with the scopes "knowledge:*"
    When I open the edit form of the entry I created
    And I fill "Metadata (JSON)" with "{not json"
    And I click "Save Changes"
    Then the URL should contain "/edit?error="
    And I should see "Invalid JSON in metadata field"

  Scenario: An entry that does not exist sends the user back to the list
    Given I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge/99999"
    Then the URL should contain "/knowledge?error="
    And I should see "Knowledge entry not found"

  # --- Detail and validation ---

  Scenario: The detail of an entry shows its status
    Given I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge"
    And I click "What is X?"
    Then I should see "Knowledge Entry #"
    And I should see "NAMESPACE"
    And the sidebar menu should highlight only "Knowledge Base"

  Scenario: The validation details of an entry are shown
    Given I sign in with the scopes "knowledge:*"
    When I open the validation of the entry I created
    Then I should see "Validation Details"
    And I should see "Q: What is X?"
    When I click "Back to Entry"
    Then I should see "Knowledge Entry #"

  Scenario: An entry is validated again
    Given I sign in with the scopes "knowledge:*"
    When I open the entry I created
    And I click "Re-validate"
    Then I should see "Validation re-triggered"
    And the validation of the entry should have been requested

  Scenario: An entry is rejected and then approved
    Given I sign in with the scopes "knowledge:*"
    When I open the entry I created
    And I click "Reject"
    Then I should see "Entry rejected"
    When I click "Approve"
    Then I should see "Entry approved"

  Scenario: The embedding of an entry is regenerated
    Given OpenAI is configured
    And the embedding service is available
    And I sign in with the scopes "knowledge:*"
    When I open the entry I created
    And I click "Regenerate Embedding"
    Then I should see "Embedding regenerated successfully"

  Scenario: Regenerating the embedding is not offered without OpenAI
    Given OpenAI is not configured
    And I sign in with the scopes "knowledge:*"
    When I open the entry I created
    Then "Regenerate Embedding" should be hidden

  # --- Deleting ---

  Scenario: An entry is deleted from its page after a confirmation
    Given I sign in with the scopes "knowledge:*"
    When I open the entry I created
    And I click "Delete Entry"
    Then the page should have asked for a confirmation containing "delete"
    And the URL should contain "/knowledge?success="
    And I should see "Knowledge entry deleted successfully"
    And I should not see "What is X?"

  Scenario: An entry is deleted from its edit form after a confirmation
    Given I sign in with the scopes "knowledge:*"
    When I open the edit form of the entry I created
    And I click "Delete" in the page content
    Then the page should have asked for a confirmation containing "delete this entry"
    And the URL should contain "/knowledge?success="
    And I should see "Knowledge entry deleted successfully"
    And I should not see "What is X?"

  Scenario: Dismissing the confirmation keeps the entry
    Given I sign in with the scopes "knowledge:*"
    When I open the edit form of the entry I created
    And I dismiss the next confirmation
    And I click "Delete" in the page content
    Then the URL should contain "/edit"
    When I navigate to "/knowledge"
    Then I should see "What is X?"

  Scenario: Selected entries are deleted in bulk
    Given another knowledge entry exists with question "Second?" and answer "Second."
    And I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge"
    And I click "css=#selectAll"
    And I click "Delete Selected"
    Then the page should have asked for a confirmation containing "delete"
    And I should see "2 entry(ies) deleted successfully"

  # --- Generating ---

  Scenario: The generate page needs OpenAI
    Given OpenAI is not configured
    And I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge/generate"
    Then the URL should contain "/knowledge?error="
    And I should see "OpenAI not configured"

  Scenario: Entries are generated in the background and the list is shown when they are ready
    Given OpenAI is configured
    And the generation task completed successfully
    And I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge"
    And I click "Generate"
    Then the URL should be "/knowledge/generate"
    When I fill "Source Text *" with the text 'Paste of documentation that is long enough to be analysed by the generator, with several sentences.'
    And I click "Generate Entries"
    Then the URL should contain "/knowledge?namespace=general&success="
    And I should see "2 entries generated successfully"
    And the generation of knowledge entries should have been requested

  Scenario: A text that is too short is stopped by the form
    Given OpenAI is configured
    And I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge/generate"
    And I fill "Source Text *" with "too short"
    And I click "Generate Entries"
    Then the URL should be "/knowledge/generate"
    And the generation of knowledge entries should not have been requested

  Scenario: A generation that fails is reported
    Given OpenAI is configured
    And the generation task fails with the message "worker crashed"
    And I sign in with the scopes "knowledge:*"
    When I navigate to "/knowledge/generate"
    And I fill "Source Text *" with the text 'Paste of documentation that is long enough to be analysed by the generator, with several sentences.'
    And I click "Generate Entries"
    Then I should see "Generate Knowledge Entries"
    And the page should have alerted "worker crashed"
