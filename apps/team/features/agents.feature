Feature: Agent management
  An agent is an AI worker of a team, with a role, a system prompt, an LLM
  model and a configuration. Agents are managed under /platform/{team_id}/agents.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"

  Scenario: Creating an agent
    When I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer", "system_prompt": "You are a developer."}'
    Then the response status is 201
    And the response JSON field "name" is "DevAgent"
    And the response JSON field "role" is "developer"
    And the response JSON field "model" is "gpt-4o"
    And the response JSON field "provider" is "openai"
    And the response JSON field "is_active" is "True"

  Scenario: The configuration of an agent is stored as given
    When I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "Lead", "role": "cto", "provider": "anthropic", "model": "claude-sonnet-4-5", "config": {"tools": ["search_memory", "create_task"], "max_iterations": 15}}'
    Then the response status is 201
    And the response JSON field "provider" is "anthropic"
    And the response JSON field "config.tools.1" is "create_task"
    And the response JSON field "config.max_iterations" is "15"

  Scenario: Creating an agent in an unknown team
    When I send a POST request to "/platform/6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    Then the response status is 404
    And the response detail is "Team not found"

  Scenario: Reading an agent
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I remember the response field "id" as "agent_id"
    When I request "/platform/${team_id}/agents/${agent_id}"
    Then the response status is 200
    And the response JSON field "name" is "DevAgent"

  Scenario: An agent cannot be read through another team
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I remember the response field "id" as "agent_id"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Other", "slug": "other"}'
    And I remember the response field "id" as "other_team_id"
    When I request "/platform/${other_team_id}/agents/${agent_id}"
    Then the response status is 404
    And the response detail is "Agent not found"

  Scenario: Listing the agents of a team
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "A", "role": "developer"}'
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "B", "role": "sre"}'
    And I send a POST request to "/platform/team" with the JSON '{"name": "Other", "slug": "other"}'
    And I remember the response field "id" as "other_team_id"
    And I send a POST request to "/platform/${other_team_id}/agents" with the JSON '{"name": "C", "role": "developer"}'
    When I request "/platform/${team_id}/agents"
    Then the response status is 200
    And the response JSON list has 2 items

  Scenario: Updating an agent
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I remember the response field "id" as "agent_id"
    When I send a PATCH request to "/platform/${team_id}/agents/${agent_id}" with the JSON '{"model": "gpt-4o-mini", "is_active": false}'
    Then the response status is 200
    And the response JSON field "model" is "gpt-4o-mini"
    And the response JSON field "is_active" is "False"
    And the response JSON field "role" is "developer"

  Scenario: Deleting an agent
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I remember the response field "id" as "agent_id"
    When I send a DELETE request to "/platform/${team_id}/agents/${agent_id}"
    Then the response status is 204
    When I request "/platform/${team_id}/agents/${agent_id}"
    Then the response status is 404

  Scenario: Deleting a team detaches its agents
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    Then 1 agents belong to the team in the database
    When I send a DELETE request to "/platform/team/${team_id}"
    Then 0 agents belong to the team in the database
    And 1 agents without a team remain in the database

  Scenario: The agent service finds the active agents and an agent by role
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "Dev", "role": "developer"}'
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "Old SRE", "role": "sre"}'
    And I remember the response field "id" as "sre_id"
    And I send a PATCH request to "/platform/${team_id}/agents/${sre_id}" with the JSON '{"is_active": false}'
    When the agent service lists the active agents of the team
    Then the service returned the agents "Dev"
    When the agent service looks up the role "sre" in the team
    Then the service found no agent
    When the agent service looks up the role "developer" in the team
    Then the service found the agent "Dev"

  Scenario: Creating an agent needs the write scope
    Given I am authenticated with the scopes "team:platform:read"
    When I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    Then the response status is 403
