# Team AI administration

Administration of the Team AI orchestration platform: teams of AI agents with their
skills, workflows, conversations and long-term memory. As with billing and the VPN, the data lives in
another service (the team service); this feature renders its API and lets operators with
`team:write` change it, and with `team:read` look around.

## What it adds

| Module | Role |
| --- | --- |
| `internal/services/team_client.py` | HTTP client for Team API (team.internal). |
| `internal/routes/team.py` | Team AI admin routes for HTML pages. |

It also ships 13 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /team | `team:read` | Team dashboard - overview of all teams. |
| GET | /team/new | `team:write` | New team form. |
| POST | /team/new | `team:write` | Create a new team. |
| GET | /team/{team_id} | `team:read` | Team detail view with agents, workflows, conversations. |
| GET | /team/{team_id}/edit | `team:write` | Edit team form. |
| POST | /team/{team_id}/edit | `team:write` | Update a team. |
| POST | /team/{team_id}/delete | `team:write` | Delete a team. |
| GET | /team/{team_id}/agents | `team:read` | List agents for a team. |
| GET | /team/{team_id}/agents/new | `team:write` | New agent form. |
| POST | /team/{team_id}/agents/new | `team:write` | Create a new agent. |
| GET | /team/{team_id}/agents/{agent_id} | `team:read` | Agent detail view. |
| GET | /team/{team_id}/agents/{agent_id}/edit | `team:write` | Edit agent form. |
| POST | /team/{team_id}/agents/{agent_id}/edit | `team:write` | Update an agent. |
| POST | /team/{team_id}/agents/{agent_id}/delete | `team:write` | Delete an agent. |
| POST | /team/{team_id}/agents/{agent_id}/skills/new | `team:write` | Create a new skill for an agent. |
| POST | /team/{team_id}/agents/{agent_id}/skills/{skill_id}/delete | `team:write` | Delete a skill. |
| GET | /team/{team_id}/agents/{agent_id}/skills/{skill_id}/edit | `team:write` | Edit skill form. |
| POST | /team/{team_id}/agents/{agent_id}/skills/{skill_id}/edit | `team:write` | Update a skill. |
| GET | /team/{team_id}/workflows | `team:read` | List workflows for a team. |
| GET | /team/{team_id}/workflows/new | `team:write` | New workflow form. |
| POST | /team/{team_id}/workflows/new | `team:write` | Create a new workflow. |
| GET | /team/{team_id}/workflows/{workflow_id}/edit | `team:write` | Edit workflow form. |
| POST | /team/{team_id}/workflows/{workflow_id}/edit | `team:write` | Update a workflow. |
| POST | /team/{team_id}/workflows/{workflow_id}/delete | `team:write` | Delete a workflow. |
| GET | /team/{team_id}/run | `team:write` | Show the form to launch an agent conversation. |
| POST | /team/{team_id}/run | `team:write` | Create a task and trigger agent execution. |
| GET | /team/{team_id}/conversations | `team:read` | List conversations. |
| GET | /team/{team_id}/conversations/{conv_id} | `team:read` | Conversation detail with messages. |
| GET | /team/{team_id}/conversations/{conv_id}/status | `team:read` | Get conversation status and message count as JSON (for polling). |
| POST | /team/{team_id}/conversations/{conv_id}/delete | `team:write` | Delete a conversation. |
| POST | /team/{team_id}/conversations/bulk-delete | `team:write` | Bulk delete conversations. |
| POST | /team/{team_id}/conversations/{conv_id}/cancel-task | `team:write` | Cancel the task linked to a conversation. |
| POST | /team/{team_id}/conversations/bulk-cancel | `team:write` | Bulk cancel tasks linked to conversations. |
| GET | /team/{team_id}/memory | `team:read` | List memory entries for a team. |
| POST | /team/{team_id}/memory/{memory_id}/delete | `team:write` | Delete a single memory entry. |
| POST | /team/{team_id}/memory/bulk-delete | `team:write` | Bulk delete memory entries. |

Every page requests the `team` resource (`read`, `write`, `delete`) in a single exchange; destructive actions are guarded by `team:write`.

## Pages

- **Teams** (`/team`, `/team/new`, `/team/{id}`, `/edit`, `/delete`): list, create, inspect
  (agents, workflows, conversations) and remove teams.
- **Agents and skills** (`/team/{id}/agents...`): agents with their tools, and the skills attached to an agent.
- **Workflows** (`/team/{id}/workflows...`): list, create, edit and delete workflows.
- **Run** (`/team/{id}/run`): choose an agent, give a title, a message and a priority; the
  application creates a task on the team service and redirects to the team's conversations.
- **Conversations** (`/team/{id}/conversations...`): list, detail with messages, a JSON
  status endpoint that the detail page of an active conversation polls every five seconds
  (the page reloads when the status or the message count changes), deletion, and
  cancellation of the linked task - singly or in bulk.
- **Memory** (`/team/{id}/memory...`): the memory entries of a team, deletable singly or in bulk.

The bulk forms of the conversation and memory lists hold no row: the checkboxes belong to them by their `form`
attribute, because the delete form of a row cannot be nested in the bulk form. Messages and memory entries are
shown like in the chat history: their text is in the page and rendered as markdown with the same safeguards.
A skill whose name holds a quote can be deleted: the confirmation message goes through `tojson`.

## Team client

`internal.services.team_client.TeamClient` (instance `team_client`) wraps the team service's
API with typed models (`TeamInfo`, `AgentInfo`, `SkillInfo`, `ToolInfo`, `WorkflowInfo`,
`ConversationInfo`, `MessageInfo`, `TaskInfo`, `MemoryEntryInfo`). It uses the client-credentials
grant with `team:platform:read` for reads and `team:platform:write` for changes, one cached token
per scope, and an optional Unix socket transport (`TEAM_SOCKET_PATH`). Failures are logged and
produce `None`, `False` or an empty list.

## Settings

Read from environment variables (or a `.env` file) by `internal.config.Settings`.

| Variable | Default | Notes |
| --- | --- | --- |
| `TEAM_API_URL` | a placeholder URL | Team API |
| `TEAM_SOCKET_PATH` | `''` | Unix socket path (e.g., /run/team/team.sock) |

`TEAM_API_URL` is used over TCP; `TEAM_SOCKET_PATH` takes precedence when set.

## Tests

pytest:

- `tests/routes/test_team.py`
- `tests/services/test_team_client.py`
- `tests/routes/test_team_sidebar.py`

The tests cover every route handler (forms, redirects, bulk operations, the JSON status endpoint) and the team client (token handling, socket transport, each endpoint wrapper).

`tests/routes/test_team_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/team.feature`):

- View team dashboard
- View team dashboard unauthenticated
- View new team form
- Create a new team successfully
- Create a new team failure
- Create a team with invalid JSON config
- View team detail
- View team detail not found
- View team edit form
- View team edit form not found
- Update a team successfully
- Update a team failure
- Delete a team successfully
- Delete a team failure
- List agents for a team
- List agents when team not found
- View new agent form
- View new agent form when team not found
- Create an agent successfully
- Create an agent failure
- View agent detail
- View agent detail when agent not found
- View agent edit form
- Update an agent successfully
- Update an agent failure
- Delete an agent successfully
- Delete an agent failure
- List workflows for a team
- List workflows when team not found
- View new workflow form
- Create a workflow successfully
- Create a workflow failure
- Create a workflow with invalid JSON
- View workflow edit form
- View workflow edit form not found
- Update a workflow successfully
- Update a workflow failure
- Delete a workflow successfully
- Delete a workflow failure
- List conversations for a team
- List conversations when team not found
- View conversation detail
- View conversation detail not found
- Delete a conversation successfully
- Delete a conversation failure
- List memory entries for a team
- List memory when team not found
- Sidebar on the team dashboard
- Sidebar on the new team form
- Sidebar on the team detail
- Sidebar on the team edit form
- Sidebar on the agents list
- Sidebar on the new agent form
- Sidebar on the agent detail
- Sidebar on the agent edit form
- Sidebar on the skill edit form
- Sidebar on the workflows list
- Sidebar on the new workflow form
- Sidebar on the workflow edit form
- Sidebar on the run agent form
- Sidebar on the conversations list
- Sidebar on the conversation detail
- Sidebar on the memory list
- Sidebar gated links follow the scopes on the team dashboard

The team client is replaced by an `AsyncMock`; scenarios exercise teams, agents, skills, workflows, runs, conversations and memory with authorized, unauthorized and unauthenticated users.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/team.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The dashboard lists the teams
- The Team AI link leads to the dashboard
- A user without the team scope gets the access denied page
- An anonymous visitor comes back to the page asked for after the login
- A user who may only read does not see the buttons that change things
- A team is created from the form
- A team the service refuses is reported on the form
- A configuration that is not JSON is refused
- The detail of a team links to its agents, workflows and conversations
- A team that does not exist sends the user back to the dashboard
- A team is updated from its edit form
- A team the service cannot update is reported on the form
- A team is deleted after a confirmation
- Dismissing the confirmation keeps the team
- A team the service cannot delete is reported
- The agents of a team are listed
- An agent is created from the form
- Credentials are added to an agent with the form
- An agent the service refuses is reported on the form
- An agent that does not exist sends the user back to the list
- An agent is updated from its edit form
- An agent is deleted after a confirmation
- An agent the service cannot delete is reported
- A skill whose name has an apostrophe can be deleted
- The workflows of a team are listed
- A workflow is created with a step
- A workflow the service refuses is reported on the form
- A workflow is updated from its edit form
- A workflow is deleted after a confirmation
- A workflow the service cannot delete is reported
- An agent task is launched from the team page
- A task the service refuses is reported on the form
- The conversations of a team are listed with their detail
- A message with markup is shown as text
- A conversation that does not exist sends the user back to the list
- A conversation is deleted after a confirmation
- A conversation the service cannot delete is reported
- A conversation is deleted from the list after a confirmation
- Selected conversations are deleted in bulk
- The bulk actions follow the scopes
- The memory entries of a team are listed
- A memory entry with markup is shown as text
- A memory entry is deleted after a confirmation
- Selected memory entries are deleted in bulk

The pages that list conversations and memory entries show the markup of a message as text (the markdown libraries come from a CDN that the scenarios replace with empty scripts), the per-row delete buttons work next to the bulk selection, and a skill whose name holds an apostrophe can be deleted.
