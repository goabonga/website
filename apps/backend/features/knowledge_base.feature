Feature: Knowledge base semantic search
  As the chat assistant
  I want to look up curated question and answer entries by meaning
  So that answers are grounded in the knowledge of the platform

  Scenario: A public namespace is visible to everybody
    Given a namespace "faq" that is public and requires no scope
    Then the namespace should be accessible to an anonymous user

  Scenario: A private namespace without required scopes is never exposed
    Given a namespace "internal" that is private and requires no scope
    Then the namespace should not be accessible to an anonymous user
    And the namespace should not be accessible with the scopes "openid"

  Scenario: A private namespace is opened by its required scope
    Given a namespace "staff" that is private and requires the scopes "staff:read"
    Then the namespace should not be accessible to an anonymous user
    And the namespace should be accessible with the scopes "staff:read"

  Scenario: Required scopes must all be granted
    Given a namespace "billing" that is public and requires the scopes "billing:read, billing:write"
    Then the namespace should not be accessible with the scopes "billing:read"
    And the namespace should be accessible with the scopes "billing:read, billing:write"

  Scenario: Search returns the best entries with their similarity
    Given the database holds the entries:
      | id | question               | answer                | similarity |
      | 1  | How do I reset my key? | Use the account page. | 0.93       |
      | 2  | Where is my invoice?   | See the billing tab.  | 0.81       |
    When I search the knowledge base for "reset password"
    Then the search should return 2 results
    And the first result should be entry 1 with the similarity 0.93
    And the query should have been embedded

  Scenario: Search without a match returns nothing
    Given the database holds no matching entry
    When I search the knowledge base for "unrelated"
    Then the search should return 0 results
