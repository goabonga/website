Feature: Maintenance jobs
  Periodic jobs keep the platform tidy: old execution logs are purged, the
  workspaces of finished tasks are removed, and old memory entries are
  compressed into summaries. The scenarios run the Celery tasks eagerly on the
  in-memory database, with a temporary workspace and a fake language model.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"
    And the maintenance jobs use the database of the scenario

  Scenario: Old execution logs are purged
    Given an execution log entry of 100 days ago and one of 10 days ago
    When the log cleanup runs
    Then the maintenance result is '{"deleted": 1}'
    And 1 execution log entries remain

  Scenario: The age limit of the log cleanup can be changed
    Given an execution log entry of 100 days ago and one of 10 days ago
    When the log cleanup runs for entries older than 5 days
    Then the maintenance result is '{"deleted": 2}'

  Scenario: Workspaces of finished or unknown tasks are removed
    Given a workspace for a "completed" task
    And a workspace for a "failed" task
    And a workspace for a "cancelled" task
    And a workspace for an unknown task
    When the workspace cleanup runs
    Then the maintenance result is '{"deleted": 4}'
    And no task workspace remains

  Scenario: Workspaces of running or paused tasks are kept
    Given a workspace for a "in_progress" task
    And a workspace for a "paused" task
    And a workspace that is not named after a task
    When the workspace cleanup runs
    Then the maintenance result is '{"deleted": 0}'
    And 3 workspaces remain

  Scenario: Old memory entries are compressed into a summary
    Given the language model summarizes as "Deploys happen on Tuesday and Friday."
    And a memory entry "Deploy on Tuesday" of 30 hours ago
    And a memory entry "Deploy on Friday" of 26 hours ago
    And a memory entry "Fresh note" of 1 hours ago
    When the memory summarization runs
    Then the maintenance result is '{"summarized": 2}'
    And the team memory holds the contents "Deploys happen on Tuesday and Friday., Fresh note"
    And the summary entry records 2 source entries
    And the language model received "Deploy on Tuesday" and "Deploy on Friday"

  Scenario: A single old entry is not summarized
    Given the language model summarizes as "Unused"
    And a memory entry "Lonely" of 30 hours ago
    When the memory summarization runs
    Then the maintenance result is '{"summarized": 0}'
    And the team memory holds the contents "Lonely"

  Scenario: Existing summaries are not summarized again
    Given the language model summarizes as "Unused"
    And a summary memory entry "Earlier summary" of 30 hours ago
    And a memory entry "Deploy on Friday" of 26 hours ago
    When the memory summarization runs
    Then the maintenance result is '{"summarized": 0}'

  Scenario: A failing language model keeps the entries
    Given the language model fails
    And a memory entry "Deploy on Tuesday" of 30 hours ago
    And a memory entry "Deploy on Friday" of 26 hours ago
    When the memory summarization runs
    Then the maintenance result is '{"summarized": 0}'
    And the team memory holds the contents "Deploy on Tuesday, Deploy on Friday"

  Scenario: Without an API key the summarization is skipped
    Given no language model key is configured
    And a memory entry "Deploy on Tuesday" of 30 hours ago
    And a memory entry "Deploy on Friday" of 26 hours ago
    When the memory summarization runs
    Then the maintenance result is '{"summarized": 0}'
    And the team memory holds the contents "Deploy on Tuesday, Deploy on Friday"

  Scenario: The maintenance jobs are scheduled
    Then the Celery beat schedule runs "team.tasks.cleanup_tasks.cleanup_old_logs" every 86400 seconds
    And the Celery beat schedule runs "team.tasks.cleanup_tasks.cleanup_stale_workspaces" every 3600 seconds
    And the Celery beat schedule runs "team.tasks.memory_tasks.summarize_memory" every 3600 seconds
