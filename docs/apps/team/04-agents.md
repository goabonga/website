# Agents

An agent is an AI worker that belongs to a team. It has a role in the team, a
system prompt, an LLM provider and model, and a configuration that later
features read (the tools it may use, its credentials, its iteration limit).
This feature adds the agent endpoints and a small service to look agents up.

## Endpoints

All routes are under `/platform/{team_id}/agents`. They check that the team
exists (`404 Team not found`) and scope the lookups to it, so an agent cannot
be read through another team (`404 Agent not found`).

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| POST | `/platform/{team_id}/agents` | `team:platform:write` | Create an agent (`201`) |
| GET | `/platform/{team_id}/agents` | `team:platform:read` | List the agents of the team, newest first (`limit`, `offset`) |
| GET | `/platform/{team_id}/agents/{agent_id}` | `team:platform:read` | Read an agent |
| PATCH | `/platform/{team_id}/agents/{agent_id}` | `team:platform:write` | Update `name`, `role`, `description`, `system_prompt`, `model`, `provider`, `config` or `is_active` |
| DELETE | `/platform/{team_id}/agents/{agent_id}` | `team:platform:write` | Delete an agent (`204`) |

Creation takes `name` and `role` (both required) and optionally
`description`, `system_prompt`, `model` (default `gpt-4o`), `provider`
(default `openai`) and `config` (default `{}`).

## Data model and migration

Table `agents` (model `team.models.Agent`, schemas `AgentCreate`,
`AgentUpdate`, `AgentResponse`), created by revision `0002_create_agents`:
`id`, `team_id` (foreign key to `teams`, `ON DELETE CASCADE`, nullable,
indexed), `name` (indexed), `role`, `description`, `system_prompt`, `model`,
`provider`, `is_active`, `config` (JSONB) and `created_at`.

Deleting a team goes through the ORM, which first detaches the agents of the
team (their `team_id` becomes `NULL`) instead of deleting them; the
`ON DELETE CASCADE` rule of the database is not what runs. Delete the agents
of a team before deleting the team if they must disappear.

`config` is stored as given. The keys the application understands appear in
later pages, for example `tools` (the names of the tools the agent may call),
`max_iterations` and `credentials`.

`team.services.AgentService` offers `get_active_agents(team_id)` and
`get_agent_by_role(team_id, role)`; the second returns the active agent with
that role, if any.

## Settings

No new setting.

## Tests

pytest: `tests/test_routes_agents.py` covers the five endpoints (creation with
defaults and with every field, listing, reading, partial update, deletion,
unknown team and unknown agent, validation errors, missing scope and missing
authentication), `tests/test_services_agent.py` covers the service, and the
models and schemas tests gain the agent cases.

behave (`features/agents.feature`):

- Creating an agent
- The configuration of an agent is stored as given
- Creating an agent in an unknown team
- Reading an agent
- An agent cannot be read through another team
- Listing the agents of a team
- Updating an agent
- Deleting an agent
- Deleting a team detaches its agents
- The agent service finds the active agents and an agent by role
- Creating an agent needs the write scope

The scenarios run the routes and the service against the in-memory SQLite
database described in [Teams](03-teams.md).
