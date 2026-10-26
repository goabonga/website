# Maintenance

Three periodic Celery tasks keep the platform tidy: they purge the old
execution logs, remove the workspaces that finished tasks left behind, and
compress old memory entries. They are scheduled with Celery beat (see
[Task dispatch](16-task-dispatch.md) for how to run the scheduler).

## Log purge

`team.tasks.cleanup_tasks.cleanup_old_logs(days_old=90)` deletes the
`execution_logs` rows older than `days_old` days and returns `{"deleted":
<number>}`. Scheduled every 24 hours with the default of 90 days. Usage events
([Usage reporting](10-usage.md)) are rows of the same table and are purged with
the others.

## Workspace cleanup

`team.tasks.cleanup_tasks.cleanup_stale_workspaces()` is the safety net of the
workspace deletion done at the end of each run ([Agent runner](15-agent-runner.md)).
It looks at the directories of `WORKSPACE_DIR` whose name is a UUID (a task
workspace) and removes those whose task does not exist or is `completed`,
`failed` or `cancelled`. Directories of `pending`, `assigned`, `in_progress` or
`paused` tasks (a paused task will run again), files, and directories with
another name are left alone. It returns `{"deleted": <number>}`. Scheduled every
hour.

## Memory summarization

`team.tasks.memory_tasks.summarize_memory()` compresses the long-term memory
([Memory](06-memory.md)). For each active team it takes up to 100 entries older
than 24 hours, ignores the entries that are already summaries
(`extra.is_summary`) and, when at least two remain, asks a language model to
summarize them into one paragraph. The entries are replaced by one new entry
whose `extra` is `{"is_summary": true, "source_count": <number>}` and whose
embedding is computed again. The model is OpenAI `gpt-4o` when an OpenAI key is
configured, otherwise Anthropic `claude-sonnet-4-5-20250929` (see
[LLM completions](14-llm.md)). When the model fails for a team its entries are
kept, and when neither key is configured nothing is done. It returns
`{"summarized": <number of entries replaced>}`. Scheduled every hour.

## Beat

The schedule entries are `cleanup-old-logs-daily`,
`cleanup-stale-workspaces-hourly` and `summarize-memory-hourly`.

## Settings

No new setting: the tasks use `WORKSPACE_DIR`, `OPENAI_API_KEY` and
`ANTHROPIC_API_KEY` described in the previous pages.

## Tests

pytest: `tests/test_tasks_cleanup.py` and `tests/test_tasks_memory.py` cover
the three tasks (cut-off dates, directory classification, grouping, summaries,
provider choice, failure handling), and `tests/test_celery.py` checks the
schedule entries.

behave (`features/maintenance.feature`), with a temporary workspace and a fake
language model:

- Old execution logs are purged
- The age limit of the log cleanup can be changed
- Workspaces of finished or unknown tasks are removed
- Workspaces of running or paused tasks are kept
- Old memory entries are compressed into a summary
- A single old entry is not summarized
- Existing summaries are not summarized again
- A failing language model keeps the entries
- Without an API key the summarization is skipped
- The maintenance jobs are scheduled
