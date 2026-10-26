Feature: Collections
  As an API client
  I want to create and manage collections of documents
  So that I can organize my knowledge base

  Background:
    Given I am authenticated as user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "collections:read collections:write"
    And the collections data layer is in memory

  Scenario: Create a personal collection
    When I send a POST request to "/api/v1/collections" with JSON
      """
      {"name": "Handbook", "slug": "handbook", "description": "Team handbook"}
      """
    Then the response status code should be 201
    And the response JSON "slug" should be "handbook"
    And the response JSON "name" should be "Handbook"
    And the response JSON "document_count" should be "0"

  Scenario: A duplicate slug is rejected
    Given a collection "Handbook" with slug "handbook"
    When I send a POST request to "/api/v1/collections" with JSON
      """
      {"name": "Other", "slug": "handbook"}
      """
    Then the response status code should be 409

  Scenario: An invalid slug is rejected
    When I send a POST request to "/api/v1/collections" with JSON
      """
      {"name": "Handbook", "slug": "Not A Slug"}
      """
    Then the response status code should be 422

  Scenario: List my collections
    Given a collection "Handbook" with slug "handbook"
    And a collection "Runbooks" with slug "runbooks"
    When I send a GET request to "/api/v1/collections"
    Then the response status code should be 200
    And the response should be a list of 2 items

  Scenario: Get a collection by slug
    Given a collection "Handbook" with slug "handbook"
    When I send a GET request to "/api/v1/collections/handbook"
    Then the response status code should be 200
    And the response JSON "name" should be "Handbook"

  Scenario: An unknown collection is not found
    When I send a GET request to "/api/v1/collections/missing"
    Then the response status code should be 404

  Scenario: Update a collection
    Given a collection "Handbook" with slug "handbook"
    When I update the collection "handbook" with JSON
      """
      {"description": "Updated"}
      """
    Then the response status code should be 200
    And the response JSON "description" should be "Updated"

  Scenario: Delete a collection
    Given a collection "Handbook" with slug "handbook"
    When I delete the collection "handbook"
    Then the response status code should be 204
    When I send a GET request to "/api/v1/collections/handbook"
    Then the response status code should be 404

  Scenario: Reading requires the read scope
    Given I am authenticated as user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "collections:write"
    When I send a GET request to "/api/v1/collections"
    Then the response status code should be 403

  Scenario: Writing requires the write scope
    Given I am authenticated as user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "collections:read"
    When I send a POST request to "/api/v1/collections" with JSON
      """
      {"name": "Handbook", "slug": "handbook"}
      """
    Then the response status code should be 403
