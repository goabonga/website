@browser
Feature: Semantic search page in a browser
  As a member of a workspace
  I want to search my documents from the web application
  So that I can find knowledge by meaning without the API

  Background:
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "free" plan
    And the workspace "Acme" contains the collection "Runbooks"
    And the workspace "Acme" contains the collection "Policies"
    And the collection "Runbooks" contains the document "restart the payment service after a failed deploy"
    And the collection "Runbooks" contains the document "rotate the database credentials every quarter"
    And the collection "Policies" contains the document "deploy freezes apply during the holiday season"
    And I have signed in as "Alice" through the identity provider

  Scenario: The search page is reached from the sidebar
    When I click "Search"
    Then the URL should be "/search"
    And I should see "Semantic search across your knowledge base"
    And the sidebar item "Search" should be the active one
    And the page title should be "Search - Knowledge API"

  Scenario: A query finds the documents that talk about it
    When I navigate to "/search"
    And I fill "Search Query" with "failed deploy payment service"
    And I click "All collections"
    And I click "Search"
    Then I should see "Results (1)"
    And I should see "restart the payment service after a failed deploy"
    And I should not see "rotate the database credentials"
    And the embedding model embedded "failed deploy payment service"

  Scenario: A result leads to its document
    When I navigate to "/search"
    And I fill "Search Query" with "database credentials"
    And I click "All collections"
    And I click "Search"
    And I click "View Document"
    Then I should see "Document Details"
    And I should see "rotate the database credentials every quarter"

  Scenario: The search can be limited to some collections
    When I navigate to "/search"
    And I fill "Search Query" with "deploy freezes holiday season"
    And I click "Policies"
    And I click "Search"
    Then I should see "deploy freezes apply during the holiday season"
    And I should not see "restart the payment service"

  Scenario: A query that matches nothing says so
    When I navigate to "/search"
    And I fill "Search Query" with "quantum entanglement"
    And I click "All collections"
    And I click "Search"
    Then I should see "No results found"

  Scenario: The threshold decides what is similar enough
    When I navigate to "/search"
    And I fill "Search Query" with "deploy"
    And I click "All collections"
    And I fill "Threshold" with "0.99"
    And I click "Search"
    Then I should see "No results found"

  Scenario: The filters must be a JSON object
    When I navigate to "/search"
    And I fill "Search Query" with "deploy"
    And I fill "Filters (JSON object)" with "not json"
    And I click "Search"
    Then I should see "Filters must be valid JSON."

  Scenario: The search page requires a signed-in user
    Given I sign out
    When I navigate to "/search"
    Then I should be at the identity provider

  Scenario: The dashboard leads to the search page
    When I navigate to "/dashboard"
    And I click "css=.btn-secondary[href='/search']"
    Then the URL should be "/search"

  Scenario: The search page only leads to pages that exist
    When I navigate to "/search"
    Then every link of the page leads to a page of the application
    When I fill "Search Query" with "restart the payment service after a failed deploy"
    And I click "All collections"
    And I click "Search"
    Then I should see "View Document"
    And every link of the page leads to a page of the application
