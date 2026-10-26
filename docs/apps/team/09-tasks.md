# Tasks

A task is a unit of work of a team: a title, a description, a priority and an
input, optionally assigned to an agent and linked to a workflow. This feature
adds the task, agent state and execution log tables, the endpoints that create
and cancel tasks, and the orchestrator service that routes them. Running a task
with an agent comes with a later feature; at this stage a task only moves
through the statuses described below.

## Endpoints

Routes are under `/platform/{team_id}/tasks` and check that the team exists
(`404 Team not found`).

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| POST | `/platform/{team_id}/tasks` | `team:platform:write` | Create a task (`201`) |
| POST | `/platform/{team_id}/tasks/{task_id}/cancel` | `team:platform:write` | Cancel a task; `404 Task not found` |

Creation takes `title` (required), `description`, `priority` (integer, default
0, higher first), `input_data` (object), and optionally `workflow_id` and
`agent_id`. A task created with an `agent_id` starts as `assigned`, otherwise as
`pending`. There is no endpoint to read or list tasks.

Statuses: `pending`, `assigned`, `in_progress`, `completed`, `failed`,
`cancelled` and `paused`.

Cancelling a task in the `pending`, `assigned`, `paused` or `in_progress`
status:

- sets its status to `cancelled` and its `output_data` to
  `{"cancelled_from": "<previous status>"}`;
- if the task has an agent whose state records this task as the current one,
  puts the agent back to `idle` with no current task;
- sets the status of the conversation `task-<task id>` to `cancelled` when it
  is active;
- adds an `ExecutionLog` entry of type `task.cancelled` with the previous status
  and the title of the task.

A task that is `completed`, `failed` or already `cancelled` answers
`409 Task cannot be cancelled: current status is '<status>'`.

## Orchestrator service

`team.services.OrchestratorService` is the routing logic used by the
background features:

- `get_pending_tasks(team_id, limit=50)`: pending tasks, highest priority first,
  then oldest first;
- `assign_task(task, agent_id)`: sets the agent and the `assigned` status;
- `start_workflow(workflow)`: sets the workflow `active` and creates a task for
  each step that has no `depends_on`. It expects the `steps` of the workflow to
  be a list of objects with an `id` and optionally `name`, `description`,
  `role`, `priority`, `input_template` and `depends_on`; the task title is the
  step `name` (or its `id`). The workflow endpoints accept an object for
  `steps`, so a workflow whose steps are not a list yields no task.

## Data model and migration

Revision `0007_create_tasks` creates three tables:

- `tasks` (model `Task`): `id`, `team_id` (required, indexed), `workflow_id` and
  `agent_id` (optional, `SET NULL` on delete), `title`, `description` (text),
  `status`, `priority`, `input_data` and `output_data` (JSONB), `created_at`,
  `updated_at`;
- `agent_states` (model `AgentState`): the state of an agent in a conversation
  (`idle`, `thinking`, `executing` or `blocked`), its current task title and
  its last heartbeat;
- `execution_logs` (model `ExecutionLog`): an event log per team with
  `event_type`, `details` and optional links to the task, workflow and agent.

The models gain the relationships between them (`Team.workflows`, `Team.tasks`,
`Agent.states`, `Agent.tasks`, `Workflow.tasks`). As a consequence a team that
still owns tasks cannot be deleted, for the same reason as workflows (see
[Workflows](08-workflows.md)).

## Settings

No new setting.

## Tests

pytest: `tests/test_routes_tasks.py` covers creation (pending, assigned, every
field, workflow, defaults, unknown team, validation, authentication) and
cancellation (each status, agent state reset, conversation cancellation,
mismatching agent state, conflicts, unknown task and team, authentication),
`tests/test_services_orchestrator.py` covers the service, and the models and
schemas tests gain the task cases.

behave (`features/tasks.feature`):

- Creating a task without an agent leaves it pending
- Creating a task for an agent assigns it
- Creating a task in a workflow
- Creating a task in an unknown team
- A task needs a title
- Cancelling a pending task
- Cancelling a task resets its agent and closes its conversation
- A finished task cannot be cancelled (outline: completed, failed, cancelled)
- Cancelling an unknown task
- Creating a task needs the write scope
- The orchestrator lists the pending tasks by priority
- The orchestrator assigns a task to an agent
- Starting a workflow creates a task for each step without dependencies

`features/steps/tasks_steps.py` inserts tasks and agent states directly in the
in-memory database and calls the orchestrator service with a session.
