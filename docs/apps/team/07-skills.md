# Skills

A skill is a reusable set of instructions attached to an agent, following the
Agent Skills format: a short name, a description and a Markdown body. Listing
returns only the names and descriptions ("progressive disclosure"), so an agent
can see what it knows how to do without loading every body; the body is read
when the skill is needed. This feature adds the skills table and the endpoints
to manage the skills of an agent.

## Endpoints

All routes are under `/platform/{team_id}/agents/{agent_id}/skills`. They check
the team (`404 Team not found`), the agent within the team (`404 Agent not
found`) and, for a single skill, that it belongs to the agent (`404 Skill not
found`).

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| POST | `.../skills` | `team:platform:write` | Create a skill (`201`) |
| GET | `.../skills` | `team:platform:read` | List summaries (`id`, `agent_id`, `name`, `description`, `is_active`, `created_at`), newest first (`limit`, `offset`) |
| GET | `.../skills/{skill_id}` | `team:platform:read` | Read a skill with its full `content` |
| PATCH | `.../skills/{skill_id}` | `team:platform:write` | Change any field; only the fields sent are changed |
| DELETE | `.../skills/{skill_id}` | `team:platform:write` | Delete a skill (`204`) |

Fields: `name` (1-64 characters, lowercase letters and digits separated by
single hyphens, for example `code-review`; anything else gives `422`),
`description` (1-1024), `content` (Markdown, required), `license` (up to 120),
`compatibility` (up to 500), `metadata` (free-form object), `allowed_tools`
(list of tool names the skill may use) and `is_active` (default `true`).
A name can be used once per agent: a second skill with the same name for the
same agent gives `409`; another agent can use it again.

## Data model and migration

Revision `0005_create_skills` creates the table `skills` (model `Skill`):
`id`, `agent_id` and `team_id` (foreign keys with cascade, both indexed),
`name`, `description`, `content`, `license`, `compatibility`, `metadata`
(JSONB, mapped to the attribute `metadata_` because `metadata` is reserved by
SQLAlchemy), `allowed_tools` (JSONB list), `is_active`, `created_at` and
`updated_at`, with the unique constraint `uq_skill_agent_name` on
`(agent_id, name)`. Deleting an agent deletes its skills (`Agent.skills`
cascades in the ORM).

## Settings

No new setting.

## Tests

pytest: `tests/test_routes_skills.py` covers the five endpoints (creation with
every field, duplicate names, validation of the name, summaries versus full
reads, partial update including the metadata mapping, deletion, unknown team,
agent and skill, scopes and authentication) and `tests/test_schemas_skill.py`
covers the validators and the response mappings.

behave (`features/skills.feature`):

- Creating a skill
- A skill name must be lowercase words joined by hyphens
- A skill name is unique for an agent
- Two agents can have a skill with the same name
- Listing skills returns summaries and reading one returns the content
- Updating a skill
- Deleting a skill
- Skills of an unknown agent
- Creating a skill needs the write scope

The shared steps gain "the response has no field ..." for the summaries
scenario.
