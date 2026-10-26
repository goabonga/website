@browser
Feature: Knowledge namespaces in a browser
  As an operator with the namespace permissions
  I want to manage the namespaces of the knowledge base
  So that entries are grouped and protected by scope

  # --- Access and sidebar ---

  Scenario: The namespaces are listed
    Given a namespace "detail-test" with name "Detail Test" exists for namespaces
    And I sign in with the scopes "namespaces:*"
    When I navigate to "/namespaces"
    Then the page title should be "Namespaces - Internal Admin"
    And I should see "Detail Test"
    And I should see "Showing 2 of 2 namespaces"
    And the sidebar menu should highlight only "Namespaces"
    And the browser should report no errors

  Scenario: The Namespaces link leads to the list
    Given I sign in with the scopes "namespaces:*"
    When I navigate to "/namespaces/new"
    Then the sidebar menu should highlight only "Namespaces"
    When I follow the sidebar link "Namespaces"
    Then the URL should be "/namespaces"

  Scenario: A user without the namespace scope gets the access denied page
    Given I sign in with the scopes "contacts:read"
    When I navigate to "/namespaces"
    Then the page title should contain "Access Denied"
    And I should see "namespaces:read"

  Scenario: A user who may only read cannot create a namespace
    Given I sign in with the scopes "namespaces:read"
    When I navigate to "/namespaces/new"
    Then the page title should contain "Access Denied"
    And I should see "namespaces:write"

  Scenario: An anonymous visitor comes back to the page asked for after the login
    Given a user holding the scopes "namespaces:*" exists at the provider
    And a namespace "detail-test" with name "Detail Test" exists for namespaces
    When I navigate to "/namespaces?search=detail"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/namespaces?search=detail"
    And I should see "Detail Test"

  Scenario: Searching narrows the list
    Given a namespace "alpha" with name "Alpha" exists for namespaces
    And another namespace "beta" with name "Beta" exists for namespaces
    And I sign in with the scopes "namespaces:*"
    When I navigate to "/namespaces"
    And I fill "search" with "alph"
    And I click "Search"
    Then the URL should contain "search=alph"
    And I should see "Alpha"
    And I should not see "Beta"

  Scenario: The list is paginated and keeps the search
    Given 25 namespaces named "Team & Co" exist
    And a namespace "other" with name "Team other" exists for namespaces
    And I sign in with the scopes "namespaces:*"
    When I navigate to "/namespaces"
    And I fill "search" with "Team & Co"
    And I click "Search"
    Then I should see "Showing 20 of 25 namespaces"
    When I click "Next"
    Then I should see "Showing 5 of 25 namespaces"
    And I should see "Team & Co 024"

  # --- Creating and editing ---

  Scenario: A namespace is created from the form
    Given I sign in with the scopes "namespaces:*"
    When I navigate to "/namespaces"
    And I click "New Namespace"
    Then the URL should be "/namespaces/new"
    When I fill "Slug *" with "my-namespace"
    And I fill "Name *" with "My Namespace"
    And I fill "Description" with "A test namespace"
    And I click "Create Namespace"
    Then the URL should contain "/namespaces?success="
    And I should see "Namespace created successfully"
    And I should see "My Namespace"

  Scenario: A slug already in use is reported on the form
    Given a namespace "duplicate" with name "Duplicate" exists for namespaces
    And I sign in with the scopes "namespaces:*"
    When I navigate to "/namespaces/new"
    And I fill "Slug *" with "duplicate"
    And I fill "Name *" with "Duplicate again"
    And I click "Create Namespace"
    Then the URL should contain "/namespaces/new?error="
    And I should see "Namespace with slug 'duplicate' already exists"

  Scenario: A restricted namespace asks for scopes
    Given I sign in with the scopes "namespaces:*"
    When I navigate to "/namespaces/new"
    And I fill "Slug *" with "private"
    And I fill "Name *" with "Private"
    And I fill "Required Scopes" with "knowledge:read"
    And I click "css=#is_public"
    And I click "Create Namespace"
    Then the URL should contain "/namespaces?success="
    When I click "Private"
    Then I should see "knowledge:read"

  Scenario: A namespace is updated from its edit form
    Given a namespace "to-update" with name "To Update" exists for namespaces
    And I sign in with the scopes "namespaces:*"
    When I open the namespace I created
    And I click "Edit Namespace"
    Then the URL should contain "/edit"
    And the field "Name *" should contain "To Update"
    When I fill "Name *" with "Updated Namespace"
    And I click "Save Changes"
    Then the URL should contain "?success="
    And I should see "Namespace updated successfully"
    And I should see "Updated Namespace"

  Scenario: Renaming the slug of a namespace to one already in use is reported
    Given a namespace "first" with name "First" exists for namespaces
    And another namespace "second" with name "Second" exists for namespaces
    And I sign in with the scopes "namespaces:*"
    When I open the edit form of the namespace I created
    And I fill "Slug *" with "second"
    And I click "Save Changes"
    Then the URL should contain "/edit?error="
    And I should see "Namespace with slug 'second' already exists"

  Scenario: A namespace that does not exist sends the user back to the list
    Given I sign in with the scopes "namespaces:*"
    When I navigate to "/namespaces/99999"
    Then the URL should contain "/namespaces?error="
    And I should see "Namespace not found"

  # --- Deleting ---

  Scenario: A namespace is deleted from its page after a confirmation
    Given a namespace "to-delete" with name "To Delete" exists for namespaces
    And I sign in with the scopes "namespaces:*"
    When I open the namespace I created
    And I click "Delete Namespace"
    Then the page should have asked for a confirmation containing "delete this namespace"
    And the URL should contain "/namespaces?success="
    And I should see "Namespace deleted successfully"
    And I should not see "To Delete"

  Scenario: A namespace is deleted from its edit form after a confirmation
    Given a namespace "to-delete" with name "To Delete" exists for namespaces
    And I sign in with the scopes "namespaces:*"
    When I open the edit form of the namespace I created
    And I click "Delete" in the page content
    Then the page should have asked for a confirmation containing "delete this namespace"
    And the URL should contain "/namespaces?success="
    And I should see "Namespace deleted successfully"
    And I should not see "To Delete"

  Scenario: Dismissing the confirmation keeps the namespace
    Given a namespace "to-keep" with name "To Keep" exists for namespaces
    And I sign in with the scopes "namespaces:*"
    When I open the edit form of the namespace I created
    And I dismiss the next confirmation
    And I click "Delete" in the page content
    Then the URL should contain "/edit"
    When I navigate to "/namespaces"
    Then I should see "To Keep"

  Scenario: The default namespace cannot be deleted
    Given the default general namespace exists
    And I sign in with the scopes "namespaces:*"
    When I open the namespace I created
    Then "Delete Namespace" should be hidden

  Scenario: Selected namespaces are deleted in bulk
    Given a namespace "bulk-1" with name "Bulk 1" exists for namespaces
    And another namespace "bulk-2" with name "Bulk 2" exists for namespaces
    And I sign in with the scopes "namespaces:*"
    When I navigate to "/namespaces"
    And I click "css=#selectAll"
    And I click "Delete Selected"
    Then the page should have asked for a confirmation containing "delete"
    And I should see "2 namespace(s) deleted, 1 skipped (default)"
