# Workflows

A workflow is a named definition of the steps a team follows to reach a goal,
for example "build, test, ship". It has a status that tells whether it is a
draft or active. This feature adds the workflow table and the endpoints to
manage the workflows of a team.

## Endpoints

All routes are under `/platform/{team_id}/workflows`. Creation and listing
check that the team exists (`404 Team not found`); updating and deleting look
the workflow up within the team in the URL (`404 Workflow not found`). There is
no endpoint to read a single workflow: use the list.

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| POST | `/platform/{team_id}/workflows` | `team:platform:write` | Create a workflow in the `draft` status (`201`); body `name` (required), `description`, `steps` and `config` |
| GET | `/platform/{team_id}/workflows` | `team:platform:read` | List the workflows of the team, newest first (`limit`, `offset`) |
| PATCH | `/platform/{team_id}/workflows/{workflow_id}` | `team:platform:write` | Change `name`, `description`, `steps`, `status` or `config` |
| DELETE | `/platform/{team_id}/workflows/{workflow_id}` | `team:platform:write` | Delete a workflow (`204`) |

The `status` is a free string; the model documents `draft`, `active`, `paused`
and `completed`. `steps` and `config` are stored as given: the API only
requires JSON objects, and does not interpret them.

## Data model and migration

Revision `0006_create_workflows` creates the table `workflows` (model
`Workflow`): `id`, `team_id` (required foreign key to `teams`, indexed),
`name`, `description`, `steps` (JSONB), `status`, `config` (JSONB), `created_at`
and `updated_at`.

A team that still owns workflows cannot be deleted: the team deletion fails
with an internal error because the workflows cannot be detached from it.
Delete the workflows first.

## Settings

No new setting.

## Tests

pytest: `tests/test_routes_workflows.py` covers the four endpoints (creation
with defaults and with every field, listing, partial update, deletion, unknown
team and workflow, validation, scopes and authentication); the models and
schemas tests gain the workflow cases.

behave (`features/workflows.feature`):

- Creating a workflow
- Creating a workflow in an unknown team
- Listing the workflows of a team
- Activating a workflow
- A workflow cannot be changed through another team
- Deleting a workflow
- Creating a workflow needs the write scope
