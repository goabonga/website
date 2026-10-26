Feature: Task management
  A task is a unit of work of a team, optionally assigned to an agent and
  linked to a workflow. Tasks are created and cancelled under
  /platform/{team_id}/tasks; every cancellation is written to the execution log.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I remember the response field "id" as "agent_id"

  Scenario: Creating a task without an agent leaves it pending
    When I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Review PR #42"}'
    Then the response status is 201
    And the response JSON field "title" is "Review PR #42"
    And the response JSON field "status" is "pending"
    And the response JSON field "priority" is "0"
    And the response JSON field "agent_id" is "None"

  Scenario: Creating a task for an agent assigns it
    When I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Analyze logs", "agent_id": "${agent_id}", "priority": 50, "input_data": {"prompt": "Check the logs"}, "description": "Last 24 hours"}'
    Then the response status is 201
    And the response JSON field "status" is "assigned"
    And the response JSON field "agent_id" is "${agent_id}"
    And the response JSON field "priority" is "50"
    And the response JSON field "input_data.prompt" is "Check the logs"
    And the response JSON field "description" is "Last 24 hours"

  Scenario: Creating a task in a workflow
    Given I send a POST request to "/platform/${team_id}/workflows" with the JSON '{"name": "Deploy Pipeline"}'
    And I remember the response field "id" as "workflow_id"
    When I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Build", "workflow_id": "${workflow_id}"}'
    Then the response status is 201
    And the response JSON field "workflow_id" is "${workflow_id}"

  Scenario: Creating a task in an unknown team
    When I send a POST request to "/platform/6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11/tasks" with the JSON '{"title": "Review PR"}'
    Then the response status is 404
    And the response detail is "Team not found"

  Scenario: A task needs a title
    When I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"description": "No title"}'
    Then the response status is 422

  Scenario: Cancelling a pending task
    Given I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Review PR"}'
    And I remember the response field "id" as "task_id"
    When I send a POST request to "/platform/${team_id}/tasks/${task_id}/cancel"
    Then the response status is 200
    And the response JSON field "status" is "cancelled"
    And the response JSON field "output_data.cancelled_from" is "pending"
    And 1 "task.cancelled" execution log entries exist

  Scenario: Cancelling a task resets its agent and closes its conversation
    Given I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Review PR", "agent_id": "${agent_id}"}'
    And I remember the response field "id" as "task_id"
    And I send a POST request to "/platform/conversations" with the JSON '{"slug": "task-${task_id}", "title": "Review PR", "type": "task"}'
    And I remember the response field "id" as "conversation_id"
    And the agent is "executing" the task "Review PR"
    When I send a POST request to "/platform/${team_id}/tasks/${task_id}/cancel"
    Then the response status is 200
    And the agent state is "idle" without a current task
    When I request "/platform/conversations/${conversation_id}"
    Then the response JSON field "status" is "cancelled"

  Scenario Outline: A finished task cannot be cancelled
    Given a task "Done" of the team with the status "<status>"
    When I send a POST request to "/platform/${team_id}/tasks/${task_id}/cancel"
    Then the response status is 409
    And the response detail is "Task cannot be cancelled: current status is '<status>'"

    Examples:
      | status    |
      | completed |
      | failed    |
      | cancelled |

  Scenario: Cancelling an unknown task
    When I send a POST request to "/platform/${team_id}/tasks/6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11/cancel"
    Then the response status is 404
    And the response detail is "Task not found"

  Scenario: Creating a task needs the write scope
    Given I am authenticated with the scopes "team:platform:read"
    When I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Review PR"}'
    Then the response status is 403

  Scenario: The orchestrator lists the pending tasks by priority
    Given a task "Low" of the team with the priority 1
    And a task "High" of the team with the priority 9
    And a task "Mid" of the team with the priority 5
    When the orchestrator lists the pending tasks of the team
    Then the orchestrator returned the tasks "High, Mid, Low"

  Scenario: The orchestrator assigns a task to an agent
    Given a task "Review" of the team with the priority 1
    When the orchestrator assigns the task to the agent
    Then the task has the status "assigned" and belongs to the agent

  Scenario: Starting a workflow creates a task for each step without dependencies
    Given I send a POST request to "/platform/${team_id}/workflows" with the JSON '{"name": "Deploy Pipeline"}'
    And I remember the response field "id" as "workflow_id"
    And the workflow has the steps '[{"id": "build", "name": "Build", "role": "developer", "priority": 2}, {"id": "test", "depends_on": ["build"]}, {"id": "lint"}]'
    When the orchestrator starts the workflow
    Then the orchestrator created the tasks "Build, lint"
    And the workflow is "active"
