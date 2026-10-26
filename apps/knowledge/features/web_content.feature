Feature: Collection and document pages
  As a signed-in user
  I want to manage collections and documents from my browser
  So that I can build my knowledge base without writing API calls

  Background:
    Given I am a member of the workspace "Acme" on the "pro" plan
    And the content pages database is in memory
    And the content services are in memory

  Scenario: Pages require a signed-in user
    Given I am not signed in
    When I open "/collections"
    Then the response status code should be 302
    And I should be redirected to a URL starting with "/auth/login"

  Scenario: The collection list shows the collections of the workspace
    Given the workspace has a collection "Handbook"
    And the workspace has a collection "Runbooks"
    When I open "/collections"
    Then the response status code should be 200
    And the page should say "Handbook"
    And the page should say "Runbooks"

  Scenario: Another workspace's collections are not listed
    Given another workspace has a collection "Secret plans"
    When I open "/collections"
    Then the response status code should be 200
    And the page should not say "Secret plans"

  Scenario: Creating a collection derives its slug from the name
    When I create the collection "My Team Handbook" with the description "Everything we know"
    Then the response status code should be 302
    And the workspace should own a collection with slug "my-team-handbook"
    And I should be redirected to the page of the collection "my-team-handbook"

  Scenario: A collection is refused when the plan limit is reached
    Given the plan allows no more collections
    When I try to create the collection "One too many"
    Then the response status code should be 200
    And the page should say "Quota exceeded"
    And the workspace should not own a collection with slug "one-too-many"

  Scenario: Viewing a collection lists its documents
    Given the workspace has a collection "Handbook"
    And the collection "Handbook" holds the document "Reset your password from the account page"
    When I open the page of the collection "Handbook"
    Then the response status code should be 200
    And the page should say "Reset your password"

  Scenario: Viewing an unknown collection goes back to the list
    When I open "/collections/11111111-1111-1111-1111-111111111111"
    Then the response status code should be 302
    And I should be redirected to "/collections"

  Scenario: Renaming a collection
    Given the workspace has a collection "Handbook"
    When I rename the collection "Handbook" to "Team Handbook"
    Then the response status code should be 302
    And the workspace should have a collection named "Team Handbook"

  Scenario: Deleting a collection deletes its documents
    Given the workspace has a collection "Handbook"
    And the collection "Handbook" holds the document "Reset your password"
    When I remove the collection "Handbook" from the workspace
    Then the response status code should be 302
    And the workspace should have 0 collections
    And the workspace should have 0 documents

  Scenario: Deleting selected documents
    Given the workspace has a collection "Handbook"
    And the collection "Handbook" holds the document "First"
    And the collection "Handbook" holds the document "Second"
    When I delete the document "First" from the page of the collection "Handbook"
    Then the response status code should be 302
    And the collection "Handbook" should hold the documents "Second"

  Scenario: Adding a document generates its embedding
    Given the workspace has a collection "Handbook"
    When I add the text "Rotate credentials every month" to the collection "Handbook"
    Then the response status code should be 302
    And the collection "Handbook" should hold the documents "Rotate credentials every month"
    And the text "Rotate credentials every month" should have been embedded

  Scenario: Long texts can be split by markdown sections
    Given the workspace has a collection "Handbook"
    When I add a markdown text with 2 sections to the collection "Handbook" split by sections
    Then the response status code should be 302
    And the collection "Handbook" should hold 2 documents
    And every document of the collection "Handbook" should record its chunking

  Scenario: Uploading a file records its name
    Given the workspace has a collection "Handbook"
    When I upload the file "notes.txt" containing "Uploaded notes" to the collection "Handbook"
    Then the response status code should be 302
    And the collection "Handbook" should hold a document from the file "notes.txt"

  Scenario: An empty document is refused
    Given the workspace has a collection "Handbook"
    When I add the text "   " to the collection "Handbook"
    Then the response status code should be 400
    And the page should say "Content is required"

  Scenario: A document is refused when the plan limit is reached
    Given the workspace has a collection "Handbook"
    And the plan allows no more documents
    When I add the text "One too many" to the collection "Handbook"
    Then the response status code should be 200
    And the page should say "Quota exceeded"

  Scenario: Viewing a document
    Given the workspace has a collection "Handbook"
    And the collection "Handbook" holds the document "Reset your password"
    When I open the page of the document "Reset your password"
    Then the response status code should be 200
    And the page should say "Reset your password"

  Scenario: Editing a document regenerates its embedding
    Given the workspace has a collection "Handbook"
    And the collection "Handbook" holds the document "Old text"
    When I change the document "Old text" to "New text"
    Then the response status code should be 302
    And the collection "Handbook" should hold the documents "New text"
    And the text "New text" should have been embedded

  Scenario: Deleting a document
    Given the workspace has a collection "Handbook"
    And the collection "Handbook" holds the document "Reset your password"
    When I remove the document "Reset your password"
    Then the response status code should be 302
    And the workspace should have 0 documents
