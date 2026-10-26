# Task dispatch

Tasks are not only created through the API: they also arrive in bulk, from
workflows and from the agents themselves (`create_task`). This feature adds
the three Celery tasks that move work along: the dispatcher, which hands
pending tasks to agents, the auto orchestration, which periodically asks the
CEO agent to review the team, and the webhook processor, which applies events
reported by other systems. The first two are scheduled with Celery beat.

## Dispatcher

`team.tasks.dispatch_tasks.dispatch_tasks(batch_size=50)` (every 5 minutes):

- for each active team, takes at most `batch_size` tasks that are `pending` or
  `paused`, highest priority first, then oldest first;
- skips the team, with a warning, when it has no active agent;
- picks the agent: the first active agent whose `role` equals
  `input_data.role` when the task names a role, otherwise the first active
  agent of the team. A task that names a role nobody has is left untouched
  (and a warning lists the available roles);
- sets the agent and the `assigned` status (a paused task also gets its
  `output_data` cleared) and adds a `task.assigned` entry to the execution log;
- sends every assigned task to the [agent runner](15-agent-runner.md) and
  returns `{"dispatched": <number>}`.

## Auto orchestration

`team.tasks.auto_orchestrate.auto_orchestrate(team_slug="goabonga")` (every 15
minutes, for the team whose slug is `goabonga`) creates a task titled
`Autonomous team check-in`, with priority 100 and `input_data.role = "ceo"`,
for the active agent whose role is `ceo`. The agent then uses `team_status` and
`create_task` to decide what to do. The result is `{"status": "created",
"task_id": ...}` or `{"status": "skipped", "reason": ...}`, where the reason is:

| Reason | When |
|--------|------|
| `team_not_found` | no active team has this slug |
| `disabled` | `config.orchestration.enabled` of the team is `false` |
| `no_orchestrator_agent` | the team has no active `ceo` agent |
| `already_active` | a check-in task is `pending`, `assigned`, `in_progress` or `paused` |
| `too_soon` | the last finished check-in is more recent than `config.orchestration.schedule_minutes` |

`config.orchestration.prompt` replaces the default prompt of the check-in.

## Webhook events

`team.tasks.webhook_tasks.process_webhook_event(payload)` is called on demand
(`process_webhook_event.delay(payload)`); nothing in the application calls it
yet, it is the entry point for the systems that report results. The `event`
field of the payload selects the handler, and the result is `{"status":
"processed", "event": ...}`:

| Event | Payload | Effect |
|-------|---------|--------|
| `agent.task.completed` | `task_id`, `result` | The task becomes `completed` with `result` as output, and an `agent.task.completed` log entry is added |
| `agent.task.failed` | `task_id`, `error` | The task becomes `failed` with `{"error": ...}` as output, and an `agent.task.failed` log entry is added |
| `workflow.updated` | `workflow_id`, optional `status` and `config` | The workflow is updated |

An unknown event, a missing identifier or an unknown task or workflow is
logged and ignored.

## Beat

`team.celery` registers the schedule (`celery_app.conf.beat_schedule`):
`dispatch-tasks-every-5-minutes` and `auto-orchestrate-every-15-minutes`. The
scheduler must run once, next to the workers:

```bash
uv run --package team celery -A team.celery:celery_app beat --loglevel=info
```

## Settings

No new setting. The schedule and the team slug are in the code.

## Tests

pytest: `tests/test_tasks_dispatch.py`, `tests/test_tasks_auto_orchestrate.py`
and `tests/test_tasks_webhook.py` cover the three tasks (selection, role
matching, skip reasons, each event type and its edge cases), and
`tests/test_celery.py` checks the schedule entries.

behave (`features/task_dispatch.feature`), running the Celery tasks eagerly on
the in-memory database, with the hand-over to the runner recorded:

- Pending tasks are assigned to an agent and sent to the runner
- A task that asks for a role goes to the agent with that role
- A task that asks for an unknown role stays pending
- Tasks of a team without active agents wait
- The highest priorities are dispatched first
- A paused task is assigned again with a clean output
- Inactive teams are ignored by the dispatcher
- The auto orchestration creates a check-in task for the CEO
- The auto orchestration skips when there is nothing to do (outline over the five reasons)
- A webhook event completes a task
- A webhook event fails a task
- A webhook event updates a workflow
- Unknown or incomplete webhook events are ignored
- The periodic jobs are scheduled
