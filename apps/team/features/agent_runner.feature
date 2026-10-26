Feature: Agent runner
  An assigned task is executed by its agent: the runner opens a conversation
  for the task, loops between the language model and the tools of the agent
  until the model has its answer, then stores the result. It runs in a Celery
  worker; the scenarios call it in-process, with a scripted model and the
  in-memory database.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write team:read"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer", "system_prompt": "You are a developer.", "config": {"tools": ["team_status", "save_memory"], "max_iterations": 3}}'
    And I remember the response field "id" as "agent_id"
    And the agent runner is set up

  Scenario: Creating a task for an agent sends it to the runner
    When I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Review PR", "agent_id": "${agent_id}"}'
    Then the response status is 201
    And the task was sent to the agent runner
    When I send a POST request to "/platform/${team_id}/tasks" with the JSON '{"title": "Unassigned"}'
    Then the task was not sent again

  Scenario: A task is executed and completed
    Given an assigned task "Review PR" with the prompt "Review the pull request"
    And the model answers "The PR looks good"
    When the agent runner executes the task
    Then the run result status is "completed"
    And the task is "completed"
    And the task output content is "The PR looks good"
    And the model received the prompt "Review the pull request"
    And the execution log has 1 "agent.run.started" entries and 1 "agent.run.completed" entries

  Scenario: The run is recorded in a conversation
    Given an assigned task "Review PR" with the prompt "Review the pull request"
    And the model answers "The PR looks good"
    When the agent runner executes the task
    Then the conversation of the task is "completed" and belongs to the team
    And the conversation has the messages "Review the pull request, The PR looks good"
    And the agent is a participant of the conversation

  Scenario: The agent uses a tool and the model sees the result
    Given an assigned task "Status report" with the prompt "Summarise the team"
    And the model asks for the tool "team_status" with the arguments '{}'
    And the model answers "Everything is quiet"
    When the agent runner executes the task
    Then the run result status is "completed"
    And the model was called 2 times
    And the second call of the model received a tool message for "team_status"
    And the execution log has 1 "agent.tool.executed" entries and 1 "agent.run.completed" entries

  Scenario: A tool that fails is reported to the model
    Given an assigned task "Odd job" with the prompt "Do something"
    And the model asks for the tool "no_such_tool" with the arguments '{}'
    And the model answers "I could not"
    When the agent runner executes the task
    Then the run result status is "completed"
    And the second call of the model received the tool error "Unknown tool: no_such_tool"

  Scenario: The system prompt describes the team, the tools and the skills
    Given I send a POST request to "/platform/${team_id}/agents/${agent_id}/skills" with the JSON '{"name": "code-review", "description": "Review code.", "content": "Read the diff."}'
    And an assigned task "Review PR" with the prompt "Go"
    And the model answers "Done"
    When the agent runner executes the task
    Then the model system prompt contains "You are a developer."
    And the model system prompt contains "**DevAgent** → role: `developer`"
    And the model system prompt contains "Use save_memory to persist important findings"
    And the model system prompt contains "<name>code-review</name>"
    And the model was offered the tools "team_status, save_memory, activate_skill"

  Scenario: GitHub tools are hidden when no GitHub credentials are configured
    Given I send a PATCH request to "/platform/${team_id}/agents/${agent_id}" with the JSON '{"config": {"tools": ["git_clone", "github_create_pr", "team_status"]}}'
    And an assigned task "Review PR" with the prompt "Go"
    And the model answers "Done"
    When the agent runner executes the task
    Then the model was offered the tools "team_status"

  Scenario: GitHub tools are offered when credentials are configured
    Given GitHub credentials are configured
    And I send a PATCH request to "/platform/${team_id}/agents/${agent_id}" with the JSON '{"config": {"tools": ["git_clone", "team_status"]}}'
    And an assigned task "Review PR" with the prompt "Go"
    And the model answers "Done"
    When the agent runner executes the task
    Then the model was offered the tools "git_clone, team_status"

  Scenario: The loop stops at the maximum number of iterations
    Given an assigned task "Endless" with the prompt "Loop"
    And the model asks for the tool "team_status" with the arguments '{}'
    And the model asks for the tool "team_status" with the arguments '{}'
    And the model asks for the tool "team_status" with the arguments '{}'
    When the agent runner executes the task
    Then the run result status is "completed"
    And the model was called 3 times

  Scenario: A task that is not assigned is skipped
    Given a pending task "Waiting" of the team
    When the agent runner executes the task
    Then the run result status is "skipped"
    And the model was called 0 times

  Scenario: A task whose agent no longer exists fails
    Given an assigned task "Orphan" with the prompt "Go"
    And I send a DELETE request to "/platform/${team_id}/agents/${agent_id}"
    When the agent runner executes the task
    Then the run result status is "failed"
    And the task is "failed"
    And the task output error is "Agent not found"

  Scenario: A failure of the model fails the task
    Given an assigned task "Review PR" with the prompt "Go"
    And the model fails with "provider unavailable"
    When the agent runner executes the task
    Then the run result status is "failed"
    And the task is "failed"
    And the task output error is "provider unavailable"

  Scenario: A lack of credits pauses the task instead of failing it
    Given an assigned task "Review PR" with the prompt "Go"
    And the model fails with "Your credit balance is too low to access the API"
    When the agent runner executes the task
    Then the run result status is "paused"
    And the task is "paused"

  Scenario: A task cancelled while the agent works is stopped
    Given an assigned task "Review PR" with the prompt "Go"
    And the model asks for the tool "team_status" with the arguments '{}' and the task is cancelled meanwhile
    And the model answers "Never sent"
    When the agent runner executes the task
    Then the run result status is "cancelled"
    And the task is "cancelled"
    And the conversation of the task is "cancelled" and belongs to the team
    And the execution log has 1 "agent.run.cancelled" entries and 0 "agent.run.completed" entries

  Scenario: A completed step starts the next step of its workflow
    Given an active workflow with the steps '[{"id": "build", "name": "Build"}, {"id": "test", "name": "Test", "depends_on": ["build"]}]'
    And the workflow task for the step "build" is assigned to the agent
    And the model answers "Built v1"
    When the agent runner executes the task
    Then the workflow has a pending task "Test" that received the result "Built v1" of the step "build"
    When the workflow task for the step "test" is assigned to the agent
    And the model answers "Tested"
    And the agent runner executes the task
    Then the workflow is "completed"
    And the execution log has 1 "workflow.completed" entries and 2 "agent.run.completed" entries

  Scenario: The workspace of the task is removed after the run
    Given an assigned task "Write notes" with the prompt "Take notes"
    And the model asks for the tool "dir_mkdir" with the arguments '{"path": "notes"}'
    And the model answers "Done"
    When the agent runner executes the task
    Then the run result status is "completed"
    And no workspace remains for the task

  Scenario: The Celery task runs the agent
    Given an assigned task "Review PR" with the prompt "Go"
    And the model answers "Done"
    When the Celery task run_agent_task is executed for the task
    Then the Celery result status is "completed"
    And the task is "completed"

  Scenario: The Celery application is configured for the team queue
    Then the Celery application uses the default queue "team"
    And the Celery application includes the task module "team.tasks.agent_runner"
    And the Celery task "team.tasks.agent_runner.run_agent_task" is registered
