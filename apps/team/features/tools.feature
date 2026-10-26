Feature: Tool registry
  Agents act through tools: functions registered by name with a description
  and a parameter schema, which the model can call. The catalog is exposed
  under /platform/tools and the tools run with the database session, the team
  and the agent of the task that calls them.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write"
    And no OpenAI API key is configured
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I remember the response field "id" as "agent_id"

  Scenario: The catalog lists the registered tools
    When I request "/platform/tools"
    Then the response status is 200
    And the catalog contains the tools "create_task, http_request, save_memory, search_memory, update_memory, delete_memory, activate_skill, team_status"
    And every tool of the catalog has a description and parameters

  Scenario: The catalog needs authentication
    Given I am not authenticated
    When I request "/platform/tools"
    Then the response status is 401

  Scenario: Tool definitions use the function calling format and skip unknown tools
    When the definitions of the tools "team_status, no_such_tool" are requested
    Then 1 tool definitions are returned
    And the definition of "team_status" has the type "function"

  Scenario: An unknown tool is reported as an error
    When the agent runs the tool "no_such_tool" with '{}'
    Then the tool result field "error" is "Unknown tool: no_such_tool"

  Scenario: Creating a sub-task records which agent created it
    When the agent runs the tool "create_task" with '{"title": "Write tests", "priority": 3}'
    Then the tool result field "status" is "pending"
    And the tool result field "title" is "Write tests"
    And the team has a pending task "Write tests" created by the agent "DevAgent"

  Scenario: A sub-task can only target an existing role
    When the agent runs the tool "create_task" with '{"title": "Deploy", "input_data": {"role": "wizard"}}'
    Then the tool result field "error" is "No agent with role 'wizard'"
    And the tool result field "available_roles.0" is "developer"

  Scenario: Saving and searching the team memory
    When the agent runs the tool "save_memory" with '{"content": "Deploys happen on Tuesday", "extra": {"source": "retro"}}'
    Then the tool result field "saved" is "True"
    When the agent runs the tool "search_memory" with '{"query": "Tuesday"}'
    Then the tool result field "search_type" is "keyword"
    And the tool result field "results.0.content" is "Deploys happen on Tuesday"
    When the agent runs the tool "search_memory" with '{"query": "Friday"}'
    Then the tool result has no results

  Scenario: Updating and deleting a memory entry
    Given the agent runs the tool "save_memory" with '{"content": "Old fact"}'
    And I remember the tool result field "memory_id" as "memory_id"
    When the agent runs the tool "update_memory" with '{"memory_id": "${memory_id}", "content": "New fact"}'
    Then the tool result field "updated" is "True"
    When the agent runs the tool "search_memory" with '{"query": "New fact"}'
    Then the tool result field "results.0.content" is "New fact"
    When the agent runs the tool "delete_memory" with '{"memory_id": "${memory_id}"}'
    Then the tool result field "deleted" is "True"
    When the agent runs the tool "delete_memory" with '{"memory_id": "${memory_id}"}'
    Then the tool result field "error" is "Memory entry not found: ${memory_id}"

  Scenario: Activating a skill returns its instructions
    Given I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "code-review", "description": "Review code.", "content": "Read the diff first."}'
    When the agent runs the tool "activate_skill" with '{"skill_name": "code-review"}'
    Then the tool result field "skill_name" is "code-review"
    And the tool result field "instructions" is "Read the diff first."

  Scenario: Activating an unknown skill explains what to do
    When the agent runs the tool "activate_skill" with '{"skill_name": "missing"}'
    Then the tool result field "error" is "Skill 'missing' not found or inactive"

  Scenario: The team status summarises agents and tasks
    Given I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Review PR"}'
    When the agent runs the tool "team_status" with '{}'
    Then the tool result field "agents.0.name" is "DevAgent"
    And the tool result field "agents.0.state" is "idle"
    And the tool result field "task_counts.pending" is "1"
    And the tool result field "pending_tasks.0.title" is "Review PR"

  Scenario: http_request calls an external API
    Given an external API answering "pong" with the status 200
    When the agent runs the tool "http_request" with '{"url": "https://api.example.com/ping", "method": "get"}'
    Then the tool result field "status_code" is "200"
    And the tool result field "body" is "pong"
    And the external API received a GET request on "/ping"
