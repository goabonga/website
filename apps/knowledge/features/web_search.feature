Feature: Search page
  As a signed-in user
  I want to search my documents from the browser
  So that I find relevant passages without using the API

  Background:
    Given I am a member of the workspace "Acme" on the "pro" plan
    And the content pages database is in memory
    And the content services are in memory
    And the embedder is keyword based
    And the web search is in memory
    And the workspace has a collection "Handbook"
    And the workspace has a collection "Runbooks"
    And the collection "Handbook" holds the document "reset your password from the account page"
    And the collection "Runbooks" holds the document "rotate the database credentials every month"
    And the collection "Runbooks" holds the document "password policy requires twelve characters"

  Scenario: The search page requires a signed-in user
    Given I am not signed in
    When I open "/search"
    Then the response status code should be 302
    And I should be redirected to a URL starting with "/auth/login"

  Scenario: The empty search page offers the collections of the workspace
    When I open "/search"
    Then the response status code should be 200
    And the page should say "Handbook"
    And the page should say "Runbooks"
    And the page should not say "Results ("

  Scenario: A query lists the best matches first
    When I open "/search?q=reset+password&threshold=0.1"
    Then the response status code should be 200
    And the page should say "Results ("
    And the page should say "reset your password from the account page"

  Scenario: A search can be restricted to one collection
    When I open "/search?q=password&threshold=0.1&collection_ids=runbooks"
    Then the response status code should be 200
    And the page should say "password policy requires twelve characters"
    And the page should not say "reset your password from the account page"

  Scenario: Weak matches are filtered by the threshold
    When I open "/search?q=database+credentials&threshold=0.95"
    Then the response status code should be 200
    And the page should say "No results found"

  Scenario: Invalid JSON filters are reported
    When I open "/search?q=password&filters_json=%7Bnot-json"
    Then the response status code should be 200
    And the page should say "Filters must be valid JSON."

  Scenario: A failing search is reported on the page
    Given the search backend is failing
    When I open "/search?q=password"
    Then the response status code should be 200
    And the page should say "Search failed"

  Scenario: Submitting the form redirects to a shareable URL
    When I submit the search form for "reset password" in the collections "handbook" and "runbooks"
    Then the response status code should be 302
    And I should be redirected to a URL starting with "/search?q=reset+password&collection_ids=handbook%2Crunbooks"
