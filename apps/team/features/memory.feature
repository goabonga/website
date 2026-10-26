Feature: Shared memory
  A team keeps memory entries: pieces of text that agents and users want to
  remember, each stored with an embedding vector for semantic search. Entries
  are managed under /platform/{team_id}/memory.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write"
    And embeddings are computed by a fake model
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"

  Scenario: Creating a memory entry computes its embedding
    When I send a POST request to "/platform/${team_id}/memory" with the JSON '{"content": "Deploys happen on Tuesday", "extra": {"source": "retro"}}'
    Then the response status is 201
    And the response JSON field "content" is "Deploys happen on Tuesday"
    And the response JSON field "extra.source" is "retro"
    And the embedding model received "Deploys happen on Tuesday"
    And the stored embedding of the entry starts with 25.0

  Scenario: Updating the content computes a new embedding
    Given I send a POST request to "/platform/${team_id}/memory" with the JSON '{"content": "Old"}'
    And I remember the response field "id" as "entry_id"
    When I send a PATCH request to "/platform/${team_id}/memory/${entry_id}" with the JSON '{"content": "A much newer content"}'
    Then the response status is 200
    And the response JSON field "content" is "A much newer content"
    And the stored embedding of the entry starts with 20.0

  Scenario: Updating only the metadata keeps the embedding
    Given I send a POST request to "/platform/${team_id}/memory" with the JSON '{"content": "Old"}'
    And I remember the response field "id" as "entry_id"
    When I send a PATCH request to "/platform/${team_id}/memory/${entry_id}" with the JSON '{"extra": {"pinned": true}}'
    Then the response status is 200
    And the response JSON field "extra.pinned" is "True"
    And the embedding model received 1 texts
    And the stored embedding of the entry starts with 3.0

  Scenario: Listing the memory of a team
    Given I send a POST request to "/platform/${team_id}/memory" with the JSON '{"content": "First"}'
    And I send a POST request to "/platform/${team_id}/memory" with the JSON '{"content": "Second"}'
    And I send a POST request to "/platform/team" with the JSON '{"name": "Other", "slug": "other"}'
    And I remember the response field "id" as "other_team_id"
    And I send a POST request to "/platform/${other_team_id}/memory" with the JSON '{"content": "Not ours"}'
    When I request "/platform/${team_id}/memory"
    Then the response status is 200
    And the response JSON list has 2 items

  Scenario: Deleting a memory entry
    Given I send a POST request to "/platform/${team_id}/memory" with the JSON '{"content": "Forget me"}'
    And I remember the response field "id" as "entry_id"
    When I send a DELETE request to "/platform/${team_id}/memory/${entry_id}"
    Then the response status is 204
    When I send a DELETE request to "/platform/${team_id}/memory/${entry_id}"
    Then the response status is 404
    And the response detail is "Memory entry not found"

  Scenario: An entry cannot be changed through another team
    Given I send a POST request to "/platform/${team_id}/memory" with the JSON '{"content": "Ours"}'
    And I remember the response field "id" as "entry_id"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Other", "slug": "other"}'
    And I remember the response field "id" as "other_team_id"
    When I send a PATCH request to "/platform/${other_team_id}/memory/${entry_id}" with the JSON '{"content": "Mine now"}'
    Then the response status is 404

  Scenario: Memory of an unknown team
    When I request "/platform/6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11/memory"
    Then the response status is 404
    And the response detail is "Team not found"

  Scenario: Creating a memory entry needs the write scope
    Given I am authenticated with the scopes "team:platform:read"
    When I send a POST request to "/platform/${team_id}/memory" with the JSON '{"content": "Nope"}'
    Then the response status is 403

  Scenario: Without an OpenAI key the embedding is a zero vector
    Given no OpenAI API key is configured
    When an embedding is generated for "hello"
    Then the embedding has 1536 dimensions and only zeros

  Scenario: The memory service returns the most recent entries of a team and of an agent
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I remember the response field "id" as "agent_id"
    And I send a POST request to "/platform/${team_id}/memory" with the JSON '{"content": "Shared"}'
    And I send a POST request to "/platform/${team_id}/memory" with the JSON '{"content": "Mine", "agent_id": "${agent_id}"}'
    When the memory service lists the recent entries of the team
    Then the service returned 2 entries
    When the memory service lists the entries of the agent
    Then the service returned 1 entries
