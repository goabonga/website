@browser
Feature: Collection and document pages in a browser
  As a member of a workspace
  I want to manage collections and documents in the web application
  So that I can organise the knowledge of my team without the API

  Background:
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And I have signed in as "Alice" through the identity provider

  Scenario: The collection list starts empty and offers to create a collection
    When I click "Collections"
    Then the URL should be "/collections"
    And I should see "No collections yet"
    When I click "Create Collection"
    Then the URL should be "/collections/new"

  Scenario: A collection is created from the form
    When I navigate to "/collections/new"
    And I fill "Name" with "Team Handbook"
    And I fill "Description" with "Everything a newcomer should read"
    And I click "Create Collection"
    Then the page title should be "Team Handbook - Knowledge API"
    And I should see "Everything a newcomer should read"
    And I should see "No documents yet"
    When I click "Collections"
    Then I should see "Team Handbook"
    And the workspace "Acme" should hold the collection "Team Handbook"

  Scenario: Two collections cannot share a name
    Given the workspace "Acme" contains the collection "Team Handbook"
    When I navigate to "/collections/new"
    And I fill "Name" with "Team Handbook"
    And I click "Create Collection"
    Then I should see "already exists"
    And the URL should be "/collections/new"

  Scenario: The plan limits the number of collections
    Given the workspace "Acme" contains the collection "One"
    And the workspace "Acme" contains the collection "Two"
    And the workspace "Acme" contains the collection "Three"
    When I navigate to "/collections/new"
    And I fill "Name" with "Four"
    And I click "Create Collection"
    Then I should see "quota"
    And the workspace "Acme" should hold 3 collections

  Scenario: A collection is renamed
    Given the workspace "Acme" contains the collection "Handbook"
    When I navigate to "/collections"
    And I click "Edit"
    And I fill "Name" with "Employee Handbook"
    And I click "Save Changes"
    Then I should see "Employee Handbook"
    And the workspace "Acme" should hold the collection "Employee Handbook"

  Scenario: A document is added to a collection
    Given the workspace "Acme" contains the collection "Handbook"
    When I navigate to "/collections"
    And I click "Handbook"
    And I click "Add Document"
    And I fill "Content" with "Staging deploys run every night at two"
    And I fill "Source Type" with "wiki"
    And I click "Create Document"
    Then the URL should contain "/collections/"
    And I should see "Staging deploys run every night at two"
    And the embedding model embedded "Staging deploys run every night at two"
    And the sidebar item "Collections" should be the active one

  Scenario: A document needs some content
    Given the workspace "Acme" contains the collection "Handbook"
    When I open the new document form of "Handbook"
    And I fill "Content" with "   "
    And I click "Create Document"
    Then I should see "Content is required"

  Scenario: A text file is uploaded as a document
    Given the workspace "Acme" contains the collection "Handbook"
    When I open the new document form of "Handbook"
    And I choose the file "notes.txt" containing "Backups are kept for thirty days" in the upload field
    And I click "Create Document"
    Then I should see "Backups are kept for thirty days"
    When I click "Backups are kept for thirty days"
    Then I should see "notes.txt"

  Scenario: A document is read, edited and deleted
    Given the workspace "Acme" contains the collection "Handbook"
    And the collection "Handbook" contains the document "First draft of the runbook"
    And the browser accepts the confirmation dialogs
    When I navigate to "/collections"
    And I click "Handbook"
    And I click "First draft of the runbook"
    Then I should see "Document Details"
    When I click "Edit"
    And I fill "Content" with "Final version of the runbook"
    And I click "Save Changes"
    Then I should see "Final version of the runbook"
    When I click "Delete"
    Then I should see "No documents yet"

  Scenario: Several documents are deleted at once
    Given the workspace "Acme" contains the collection "Handbook"
    And the collection "Handbook" contains the document "Alpha note"
    And the collection "Handbook" contains the document "Beta note"
    And the collection "Handbook" contains the document "Gamma note"
    And the browser accepts the confirmation dialogs
    When I navigate to "/collections"
    And I click "Handbook"
    And I select the documents "Alpha note" and "Beta note"
    And I click "Delete Selected"
    Then I should not see "Alpha note"
    And I should see "Gamma note"

  Scenario: A collection is deleted with its documents
    Given the workspace "Acme" contains the collection "Handbook"
    And the collection "Handbook" contains the document "Alpha note"
    And the browser accepts the confirmation dialogs
    When I navigate to "/collections"
    And I click "Handbook"
    And I click "Delete"
    Then the URL should be "/collections"
    And I should see "No collections yet"

  Scenario: The collection of another workspace is out of reach
    Given a user "Bob" who holds every knowledge scope
    And "Bob" owns the workspace "Rival" on the "free" plan
    And the workspace "Rival" contains the collection "Secrets"
    When I open the collection "Secrets" of the workspace "Rival"
    Then the URL should be "/collections"
    And I should not see "Secrets"

  Scenario: The dashboard leads to the collection pages
    When I navigate to "/dashboard"
    And I click "Create Collection"
    Then the URL should be "/collections/new"
    When I navigate to "/dashboard"
    And I click "All Collections"
    Then the URL should be "/collections"

  Scenario: The collection pages only lead to pages that exist
    Given the workspace "Acme" contains the collection "Handbook"
    And the collection "Handbook" contains the document "Alpha note"
    When I navigate to "/dashboard"
    Then every link of the page leads to a page of the application
    When I click "Collections"
    Then the sidebar item "Collections" should be the active one
    And every link of the page leads to a page of the application
    When I click "New Collection"
    Then every link of the page leads to a page of the application
    When I navigate to "/collections"
    And I click "Handbook"
    Then every link of the page leads to a page of the application
    When I click "Alpha note"
    Then the sidebar item "Collections" should be the active one
    And every link of the page leads to a page of the application
