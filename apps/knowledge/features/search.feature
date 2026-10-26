Feature: Semantic search
  As an API client
  I want to search my documents by meaning
  So that I retrieve the most relevant passages for a question

  Background:
    Given I am authenticated as user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "collections:search"
    And my tenant is "cccccccc-cccc-cccc-cccc-cccccccccccc"
    And the documents data layer is in memory
    And the embedder is keyword based
    And the search data layer is in memory
    And a collection "Handbook" with slug "handbook" in my tenant
    And a collection "Runbooks" with slug "runbooks" in my tenant
    And a document "reset your password from the account page" in the collection "handbook"
    And a document "rotate the database credentials every month" in the collection "runbooks"
    And a document "password policy requires twelve characters" in the collection "runbooks"

  Scenario: Search across every collection ranks the best match first
    When I send a POST request to "/api/v1/search" with JSON
      """
      {"query": "reset password", "threshold": 0.1}
      """
    Then the response status code should be 200
    And the response JSON "query" should be "reset password"
    And the response JSON "results.0.content" should be "reset your password from the account page"
    And the response JSON "results.0.collection_slug" should be "handbook"

  Scenario: The similarity threshold filters weak matches
    When I send a POST request to "/api/v1/search" with JSON
      """
      {"query": "database credentials", "threshold": 0.9}
      """
    Then the response status code should be 200
    And the response JSON "total_results" should be "0"

  Scenario: top_k limits the number of results
    When I send a POST request to "/api/v1/search" with JSON
      """
      {"query": "password", "threshold": 0.0, "top_k": 1}
      """
    Then the response status code should be 200
    And the response JSON "total_results" should be "1"

  Scenario: Search a single collection by slug
    When I send a POST request to "/api/v1/search/collections/runbooks" with JSON
      """
      {"query": "password", "threshold": 0.1}
      """
    Then the response status code should be 200
    And the response JSON "total_results" should be "1"
    And the response JSON "results.0.collection_slug" should be "runbooks"

  Scenario: Searching an unknown collection returns no result
    When I send a POST request to "/api/v1/search/collections/missing" with JSON
      """
      {"query": "password", "threshold": 0.0}
      """
    Then the response status code should be 200
    And the response JSON "total_results" should be "0"

  Scenario: Content can be left out of the results
    When I send a POST request to "/api/v1/search" with JSON
      """
      {"query": "reset password", "threshold": 0.1, "include_content": false}
      """
    Then the response status code should be 200
    And the response JSON "results.0.content" should be empty

  Scenario: An empty query is rejected
    When I send a POST request to "/api/v1/search" with JSON
      """
      {"query": ""}
      """
    Then the response status code should be 422

  Scenario: top_k above the maximum is rejected
    When I send a POST request to "/api/v1/search" with JSON
      """
      {"query": "password", "top_k": 101}
      """
    Then the response status code should be 422

  Scenario: Searching requires the search scope
    Given I am authenticated as user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "collections:read"
    When I send a POST request to "/api/v1/search" with JSON
      """
      {"query": "password"}
      """
    Then the response status code should be 403
