# Tool registry

Agents act on the platform through tools: functions registered by name, with a
description and a JSON schema of their parameters, that the language model can
call. This feature adds the registry (`ToolService`), the catalog endpoint and
the tools that work on the platform's own data. The following features add the
tools that call other services and the tools that work on a workspace.

## Endpoint

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| GET | `/platform/tools` | `team:platform:read` | List the registered tools as `{name, description, parameters}` |

Importing `team.services.tools` registers every tool of the package, which is
why the route module imports it.

## The registry

`team.services.ToolService` keeps the registered tools in a class-level
registry:

- `@ToolService.register(name, definition)` registers an async handler
  `handler(params, context) -> dict`;
- `get_tool_definitions(names)` returns the definitions in the OpenAI function
  calling format (`{"type": "function", "function": {...}}`) and skips, with a
  warning, the names that are unknown;
- `execute_tool(name, params, context)` runs a handler; an unknown name returns
  `{"error": "Unknown tool: <name>"}`. The service puts itself in the context as
  `tool_service`;
- `format_tool_result(tool_call_id, result)` builds the `tool` message sent back
  to the model;
- `get_client()` and `close()` manage a shared `httpx` client (30 s timeout).

The context given to a handler carries the database session (`db`), the
`team_id` and the `agent_id` of the task being executed, and sometimes the
`workflow_id`. Handlers never raise for an expected failure: they return an
`{"error": ...}` object that the model can read.

## Tools provided

| Tool | Parameters | What it does |
|------|------------|--------------|
| `create_task` | `title`, `description`, `input_data`, `priority` | Creates a pending task in the same team, records the creating agent in `input_data`, and refuses an `input_data.role` that matches no active agent (the error lists the available roles) |
| `http_request` | `url`, `method`, `headers`, `body` | Makes an HTTP request and returns the status code and the first 4000 characters of the body |
| `save_memory` | `content`, `extra` | Saves a memory entry with its embedding (see [Memory](06-memory.md)) |
| `search_memory` | `query`, `limit` | Cosine similarity search on the embeddings; falls back to a case-insensitive text search when no embedding key is configured (`search_type` is `vector` or `keyword`) |
| `update_memory` | `memory_id`, `content`, `extra` | Rewrites an entry and recomputes its embedding |
| `delete_memory` | `memory_id` | Deletes an entry of the team |
| `activate_skill` | `skill_name` | Returns the instructions of an active skill of the agent (see [Skills](07-skills.md)) |
| `team_status` | `hours` | Returns the active agents with their state, the task counts by status, the recently completed or failed tasks and the pending tasks |

Memory entries and skills are always looked up within the team and the agent of
the context, so a tool cannot reach the data of another team.

## Settings

No new setting.

## Tests

pytest: `tests/test_services_tool.py` (registry, definitions, execution,
`create_task`, `http_request`, result formatting and the client lifecycle),
`tests/test_routes_tools.py` (the catalog), `tests/test_tools_memory_ops.py`,
`tests/test_tools_save_memory.py`, `tests/test_tools_search_memory.py`,
`tests/test_tools_skill_ops.py` and `tests/test_tools_team_status.py`.

behave (`features/tools.feature`) runs the tools against the in-memory database
with the embedding key unset, so that the memory search uses its keyword
fallback:

- The catalog lists the registered tools
- The catalog needs authentication
- Tool definitions use the function calling format and skip unknown tools
- An unknown tool is reported as an error
- Creating a sub-task records which agent created it
- A sub-task can only target an existing role
- Saving and searching the team memory
- Updating and deleting a memory entry
- Activating a skill returns its instructions
- Activating an unknown skill explains what to do
- The team status summarises agents and tasks
- http_request calls an external API (an in-process HTTP transport plays the API)

The scenario environment provides `context.run_tool(name, params)`, which runs a
tool as the agent of the scenario with a session of its own; `features/steps/tools_steps.py`
exposes the result of the tool to the steps.
