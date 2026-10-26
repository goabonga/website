Feature: Documents
  As an API client
  I want to add documents to a collection
  So that their content is embedded and stored for later retrieval

  Background:
    Given I am authenticated as user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "documents:read documents:write"
    And my tenant is "cccccccc-cccc-cccc-cccc-cccccccccccc"
    And the documents data layer is in memory
    And a collection "Handbook" with slug "handbook" in my tenant

  Scenario: Add a single document
    When I send a POST request to "/api/v1/collections/handbook/documents/single" with JSON
      """
      {"content": "Reset a password from the account page.", "metadata": {"topic": "account"}, "source_type": "manual"}
      """
    Then the response status code should be 201
    And the response JSON "content" should be "Reset a password from the account page."
    And the response JSON "metadata.topic" should be "account"
    And the text "Reset a password from the account page." should have been embedded

  Scenario: Add several documents in one embedding batch
    When I send a POST request to "/api/v1/collections/handbook/documents" with JSON
      """
      {"documents": [{"content": "First"}, {"content": "Second"}]}
      """
    Then the response status code should be 201
    And the response should be a list of 2 items
    And the embedder should have received one batch of 2 texts

  Scenario: List the documents of a collection
    Given a document "First" in the collection "handbook"
    And a document "Second" in the collection "handbook"
    When I send a GET request to "/api/v1/collections/handbook/documents"
    Then the response status code should be 200
    And the response should be a list of 2 items

  Scenario: Get a document by id
    Given a document "First" in the collection "handbook"
    When I get the document "First"
    Then the response status code should be 200
    And the response JSON "content" should be "First"

  Scenario: Delete a document
    Given a document "First" in the collection "handbook"
    When I delete the document "First" from the collection "handbook"
    Then the response status code should be 204
    When I get the document "First"
    Then the response status code should be 404

  Scenario: Documents of an unknown collection are not found
    When I send a GET request to "/api/v1/collections/missing/documents"
    Then the response status code should be 404

  Scenario: Empty content is rejected
    When I send a POST request to "/api/v1/collections/handbook/documents/single" with JSON
      """
      {"content": ""}
      """
    Then the response status code should be 422

  Scenario: Reading documents requires the read scope
    Given I am authenticated as user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "documents:write"
    When I send a GET request to "/api/v1/collections/handbook/documents"
    Then the response status code should be 403

  Scenario: Writing documents requires the write scope
    Given I am authenticated as user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "documents:read"
    When I send a POST request to "/api/v1/collections/handbook/documents/single" with JSON
      """
      {"content": "Nope"}
      """
    Then the response status code should be 403
