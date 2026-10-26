Feature: Task dispatch
  Three Celery tasks move work along: the dispatcher assigns pending tasks to
  agents, the auto orchestration asks the CEO agent to review the team
  periodically, and the webhook processor applies events reported by other
  systems. The scenarios run them in-process against the in-memory database.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"
    And the task workers use the database of the scenario

  Scenario: Pending tasks are assigned to an agent and sent to the runner
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Review PR"}'
    And I remember the response field "id" as "task_id"
    When the dispatcher runs
    Then the dispatcher result is '{"dispatched": 1}'
    And the task titled "Review PR" is "assigned" to the agent "DevAgent"
    And 1 "task.assigned" execution log entries exist
    And the runner received the task "Review PR"

  Scenario: A task that asks for a role goes to the agent with that role
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "QaAgent", "role": "qa"}'
    And I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Test it", "input_data": {"role": "qa"}}'
    When the dispatcher runs
    Then the task titled "Test it" is "assigned" to the agent "QaAgent"

  Scenario: A task that asks for an unknown role stays pending
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Magic", "input_data": {"role": "wizard"}}'
    When the dispatcher runs
    Then the dispatcher result is '{"dispatched": 0}'
    And the task titled "Magic" is "pending" to nobody

  Scenario: Tasks of a team without active agents wait
    Given I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Lonely"}'
    When the dispatcher runs
    Then the dispatcher result is '{"dispatched": 0}'
    And the task titled "Lonely" is "pending" to nobody

  Scenario: The highest priorities are dispatched first
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Low", "priority": 1}'
    And I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "High", "priority": 9}'
    When the dispatcher runs with a batch size of 1
    Then the dispatcher result is '{"dispatched": 1}'
    And the task titled "High" is "assigned" to the agent "DevAgent"
    And the task titled "Low" is "pending" to nobody

  Scenario: A paused task is assigned again with a clean output
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Needs credit"}'
    And the task "Needs credit" is paused with the error "credit balance is too low"
    When the dispatcher runs
    Then the task titled "Needs credit" is "assigned" to the agent "DevAgent"
    And the output of the task "Needs credit" is empty

  Scenario: Inactive teams are ignored by the dispatcher
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Review PR"}'
    And I send a PATCH request to "/platform/team/${team_id}" with the JSON '{"is_active": false}'
    When the dispatcher runs
    Then the dispatcher result is '{"dispatched": 0}'

  Scenario: The auto orchestration creates a check-in task for the CEO
    Given I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "Chief", "role": "ceo"}'
    When the auto orchestration runs for the team "engineering"
    Then the orchestration status is "created"
    And the team has the task "Autonomous team check-in" with the priority 100 and the role "ceo"

  Scenario Outline: The auto orchestration skips when there is nothing to do
    Given the team has the orchestration situation "<situation>"
    When the auto orchestration runs for the team "<slug>"
    Then the orchestration is skipped because "<reason>"

    Examples:
      | situation                | slug        | reason                |
      | a ceo                    | unknown     | team_not_found        |
      | no ceo                   | engineering | no_orchestrator_agent |
      | a disabled orchestration | engineering | disabled              |
      | an active check-in       | engineering | already_active        |
      | a recent check-in        | engineering | too_soon              |

  Scenario: A webhook event completes a task
    Given I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Remote job"}'
    And I remember the response field "id" as "task_id"
    When the webhook event '{"event": "agent.task.completed", "task_id": "${task_id}", "result": {"content": "done elsewhere"}}' is processed
    Then the webhook result is "processed"
    And the task titled "Remote job" is "completed" to nobody
    And the output of the task "Remote job" has the content "done elsewhere"
    And 1 "agent.task.completed" execution log entries exist

  Scenario: A webhook event fails a task
    Given I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Remote job"}'
    And I remember the response field "id" as "task_id"
    When the webhook event '{"event": "agent.task.failed", "task_id": "${task_id}", "error": "worker crashed"}' is processed
    Then the task titled "Remote job" is "failed" to nobody
    And the output of the task "Remote job" has the error "worker crashed"

  Scenario: A webhook event updates a workflow
    Given I send a POST request to "/platform/${team_id}/workflows" with the JSON '{"name": "Pipeline"}'
    And I remember the response field "id" as "workflow_id"
    When the webhook event '{"event": "workflow.updated", "workflow_id": "${workflow_id}", "status": "paused", "config": {"retries": 3}}' is processed
    And I request "/platform/${team_id}/workflows"
    Then the response JSON field "0.status" is "paused"
    And the response JSON field "0.config.retries" is "3"

  Scenario: Unknown or incomplete webhook events are ignored
    When the webhook event '{"event": "something.else"}' is processed
    Then the webhook result is "processed"
    When the webhook event '{"event": "agent.task.completed"}' is processed
    Then the webhook result is "processed"
    And 0 "agent.task.completed" execution log entries exist

  Scenario: The periodic jobs are scheduled
    Then the Celery beat schedule runs "team.tasks.dispatch_tasks.dispatch_tasks" every 300 seconds
    And the Celery beat schedule runs "team.tasks.auto_orchestrate.auto_orchestrate" every 900 seconds
