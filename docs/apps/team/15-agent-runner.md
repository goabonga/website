# Agent runner

The agent runner executes a task with its agent. A Celery worker loads an
`assigned` task, opens a conversation for it, then loops between the language
model ([LLM completions](14-llm.md)) and the tools of the agent
([tool registry](11-tools.md)) until the model has its answer, and stores the
result in the task. This feature adds the Celery application, the
`run_agent_task` task and the dispatch of new tasks to it.

## Dispatch

`POST /platform/{team_id}/tasks` (see [Tasks](09-tasks.md)) now sends the task
to the worker as soon as it is created with an `agent_id`
(`run_agent_task.delay(task_id)`). A task created without an agent stays
`pending`.

## The run

`team.tasks.agent_runner.run_agent_task(task_id)` is a Celery task named
`team.tasks.agent_runner.run_agent_task` (declared with one retry and a 30 s delay, which the task body does not use). It runs the
asynchronous `_run_agent` on a per-thread event loop (`team.tasks.utils.run_async`),
because asyncpg connections are bound to the loop that created them.

1. The task must exist and be `assigned`, otherwise the result is
   `{"status": "skipped"}`. If its agent no longer exists the task fails with
   `Agent not found`.
2. The task becomes `in_progress`, an isolated workspace
   `<WORKSPACE_DIR>/<task id>` is created, the agent state (if any) becomes
   `thinking`, and an `agent.run.started` entry is added to the execution log.
3. A conversation `task-<task id>` of type `task` is created for the team, with
   the agent as participant. Every message of the run is stored in it.
4. The tools of the agent are taken from `config.tools`. When `GITHUB_TOKEN` and
   `GITHUB_OWNER` are not both set, the git and GitHub tools are removed so
   that the model never sees them. If the agent has active skills, the
   `activate_skill` tool is added.
5. The system prompt is the one of the agent, followed by the list of the
   active agents of the team with their roles (so that `create_task` uses valid
   roles), the usage guidelines of the tools the agent has, and the
   `<available_skills>` block (names and descriptions only).
6. The first message is built from `input_data`: `messages` if present, else
   `prompt`, else the description or the title of the task. When the task
   comes from a workflow step, the results of the previous steps
   (`parent_results`) are added in front.
7. Up to `config.max_iterations` times (default 10): the cancellation of the
   task is checked, the model is called, its answer is stored, and, if it asks
   for tools, each tool is executed with the database session, the team, the
   agent, the agent configuration and the task workspace. A tool exception
   becomes an `{"error": ...}` result. Each execution adds an
   `agent.tool.executed` entry.
8. The run ends when the model answers without asking for tools, or when the
   iterations are exhausted (the last answer is used). The task becomes
   `completed` with `output_data = {"content": ..., "conversation_id": ...}`,
   the conversation `completed`, the agent state `idle`, and an
   `agent.run.completed` entry is added.
9. If the task belongs to an active workflow whose steps are a list, the
   workflow advances: each step whose dependencies are all completed and that
   has no task yet gets a pending task carrying the results of its parents; when
   every step is completed the workflow becomes `completed` and a
   `workflow.completed` entry is added.
10. In every case the workspace of the task is deleted.

Failure handling: a task cancelled while the agent works (see the
cancellation in [Tasks](09-tasks.md)) is detected before each model call and
before completion; the run stops with `{"status": "cancelled"}`, closes the
conversation as `cancelled` and logs `agent.run.cancelled`. Any other exception
makes the task `failed` with `output_data = {"error": ...}`, except an
insufficient API credit error, which makes it `paused` so that it can be run
again once the account is credited.

Two defects of the standalone application are fixed in this migration: the
participant row of the conversation is now linked to the conversation (the
conversation is flushed before its id is used), and a workflow that completes
without creating a new task is now committed (before, its completion was
rolled back).

## Celery application

`team.celery.celery_app` (application name `team`) uses JSON serialization,
`task_acks_late`, `task_reject_on_worker_lost`, a prefetch multiplier of 1, a
one-hour time limit and a single queue named `team`. Its logging is
configured with the dual-stream setup of the [foundation](01-foundation.md)
(`LOG_LEVEL` from the environment). Start a worker with:

```bash
uv run --package team celery -A team.celery:celery_app worker --loglevel=info -Q team
```

`compose.yml` now also starts a Redis for the broker.

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CELERY_BROKER_URL` | `redis://localhost:6379/10` | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/11` | Celery result backend |
| `WORKSPACE_DIR`, `GITHUB_TOKEN`, `GITHUB_OWNER` | | See [Workspace tools](13-workspace-tools.md) |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | | See [LLM completions](14-llm.md) |

## Tests

pytest: `tests/test_tasks_agent_runner.py` covers the run (skipped, failed,
paused, cancelled and completed tasks, tool loop, iteration limit, prompt
construction, workflow progression, workspace cleanup), `tests/test_tasks_utils.py`
the event loop bridge and `tests/test_celery.py` the Celery application;
`tests/test_routes_tasks.py` now checks that creating a task for an agent
dispatches it.

behave (`features/agent_runner.feature`), with a scripted model, a temporary
workspace and the in-memory database, and with the dispatch recorded instead of
queued (`features/environment.py`):

- Creating a task for an agent sends it to the runner
- A task is executed and completed
- The run is recorded in a conversation
- The agent uses a tool and the model sees the result
- A tool that fails is reported to the model
- The system prompt describes the team, the tools and the skills
- GitHub tools are hidden when no GitHub credentials are configured
- GitHub tools are offered when credentials are configured
- The loop stops at the maximum number of iterations
- A task that is not assigned is skipped
- A task whose agent no longer exists fails
- A failure of the model fails the task
- A lack of credits pauses the task instead of failing it
- A task cancelled while the agent works is stopped
- A completed step starts the next step of its workflow
- The workspace of the task is removed after the run
- The Celery task runs the agent
- The Celery application is configured for the team queue
