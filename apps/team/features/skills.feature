Feature: Agent skills
  A skill is a set of Markdown instructions attached to an agent, following
  the Agent Skills format: a lowercase name, a description and a body that the
  agent loads when it needs it. Skills are managed under
  /platform/{team_id}/agents/{agent_id}/skills.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I remember the response field "id" as "agent_id"

  Scenario: Creating a skill
    When I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "code-review", "description": "Review code changes.", "content": "# Steps\n1. Read the diff", "allowed_tools": ["git_diff"], "metadata": {"version": "1"}}'
    Then the response status is 201
    And the response JSON field "name" is "code-review"
    And the response JSON field "allowed_tools.0" is "git_diff"
    And the response JSON field "metadata.version" is "1"
    And the response JSON field "is_active" is "True"

  Scenario: A skill name must be lowercase words joined by hyphens
    When I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "Code Review", "description": "Review.", "content": "Body"}'
    Then the response status is 422
    When I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "-code-review", "description": "Review.", "content": "Body"}'
    Then the response status is 422

  Scenario: A skill name is unique for an agent
    Given I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "code-review", "description": "Review.", "content": "Body"}'
    When I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "code-review", "description": "Again.", "content": "Body"}'
    Then the response status is 409
    And the response detail is "Skill with name 'code-review' already exists for this agent"

  Scenario: Two agents can have a skill with the same name
    Given I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "code-review", "description": "Review.", "content": "Body"}'
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "Second", "role": "developer"}'
    And I remember the response field "id" as "second_agent_id"
    When I send a POST request to "/platform/${team_id}/agents/${second_agent_id}/skills" with the JSON '{"name": "code-review", "description": "Review.", "content": "Body"}'
    Then the response status is 201

  Scenario: Listing skills returns summaries and reading one returns the content
    Given I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "code-review", "description": "Review code changes.", "content": "The full instructions"}'
    And I remember the response field "id" as "skill_id"
    When I request "/platform/${team_id}/agents/${agent_id}/skills"
    Then the response status is 200
    And the response JSON list has 1 items
    And the response JSON field "0.description" is "Review code changes."
    And the response has no field "0.content"
    When I request "/platform/${team_id}/agents/${agent_id}/skills/${skill_id}"
    Then the response JSON field "content" is "The full instructions"

  Scenario: Updating a skill
    Given I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "code-review", "description": "Review.", "content": "Body"}'
    And I remember the response field "id" as "skill_id"
    When I send a PATCH request to "/platform/${team_id}/agents/${agent_id}/skills/${skill_id}" with the JSON '{"content": "New body", "metadata": {"owner": "dev"}, "is_active": false}'
    Then the response status is 200
    And the response JSON field "content" is "New body"
    And the response JSON field "metadata.owner" is "dev"
    And the response JSON field "is_active" is "False"
    And the response JSON field "name" is "code-review"

  Scenario: Deleting a skill
    Given I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "code-review", "description": "Review.", "content": "Body"}'
    And I remember the response field "id" as "skill_id"
    When I send a DELETE request to "/platform/${team_id}/agents/${agent_id}/skills/${skill_id}"
    Then the response status is 204
    When I request "/platform/${team_id}/agents/${agent_id}/skills/${skill_id}"
    Then the response status is 404
    And the response detail is "Skill not found"

  Scenario: Skills of an unknown agent
    When I request "/platform/${team_id}/agents/6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11/skills"
    Then the response status is 404
    And the response detail is "Agent not found"

  Scenario: Creating a skill needs the write scope
    Given I am authenticated with the scopes "team:platform:read"
    When I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "code-review", "description": "Review.", "content": "Body"}'
    Then the response status is 403
