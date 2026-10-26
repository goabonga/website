# System prompts

Versioned system prompts for the platform's AI assistant. Operators can write a prompt, keep its
history, activate any earlier version and, when OpenAI is configured, have a draft generated
from a short description. Like namespaces, the prompts live in the shared database and are accessed
directly through async SQLAlchemy. This feature introduces the first OpenAI dependency and the `OPENAI_API_KEY` secret.

## What it adds

| Module | Role |
| --- | --- |
| `internal/models/prompt.py` | System prompt models with version history - mirrors fastapi-api model. |
| `internal/services/prompt_generator.py` | AI-powered system prompt generation service using OpenAI. |
| `internal/routes/prompts.py` | System Prompt CRUD routes with versioning support. |

It also ships 4 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /prompts/generate | `prompts:write` | Show form to generate a prompt using AI. |
| POST | /prompts/generate | `prompts:write` | Generate a prompt using AI from description. |
| GET | /prompts | `prompts:read` | List all prompts with pagination and search. |
| GET | /prompts/new | `prompts:write` | Show form to create a new prompt. |
| POST | /prompts/new | `prompts:write` | Create a new prompt with initial version. |
| GET | /prompts/{prompt_id} | `prompts:read` | View prompt detail with version history. |
| GET | /prompts/{prompt_id}/edit | `prompts:write` | Show form to edit a prompt (creates new version). |
| POST | /prompts/{prompt_id}/edit | `prompts:write` | Update a prompt (creates new version if content changed). |
| POST | /prompts/{prompt_id}/version/{version_id}/activate | `prompts:write` | Activate a specific version of a prompt. |
| POST | /prompts/{prompt_id}/version/{version_id}/delete | `prompts:delete` | Delete a specific version of a prompt. |
| POST | /prompts/{prompt_id}/versions/bulk-delete | `prompts:delete` | Delete multiple versions of a prompt. |
| POST | /prompts/bulk-delete | `prompts:delete` | Delete multiple prompts. |
| POST | /prompts/{prompt_id}/delete | `prompts:delete` | Delete a prompt. |

The list and detail pages request the whole `prompts` resource plus `vpn:admin` and `billing:read` (navigation).

## Versioning

Each prompt (`system_prompts`) has any number of versions (`system_prompt_versions`) and exactly one
current version. Saving an edit only creates a new version when the content changed: the version number is
the previous maximum plus one, all other versions are unset as current and the new one becomes current.
Any version can be re-activated, and versions can be deleted singly or in bulk (the pages send the selection of
a bulk delete as one comma-separated value, which the routes split).
A form cannot be nested in another one, so the Delete button of an edit form carries its own `formaction` and
confirmation: nested, the browser would drop the inner form and the button would save the page instead. A failed
save redirects back to the form with an `error` message, which the form shows.

A prompt may be flagged `is_default`
and carry `required_scopes`; its specificity is the number of required scopes. Listing the prompts
creates the default prompt ("Default Assistant", a short general-purpose instruction) when none is flagged as default.

## AI generation

`GET /prompts/generate` shows the form and `POST /prompts/generate` takes a description (at least 20
characters), a tone, optional focus areas and constraints, then asks `internal.services.prompt_generator.PromptGeneratorService`
(OpenAI chat completion, `gpt-4o-mini` by default, JSON output) for a name, slug, description and content. The result is
not saved: the user is redirected to the regular creation form (`/prompts/new?generated=1&...`) with the fields prefilled,
so a human reviews it first. Without `OPENAI_API_KEY` the form says so and the POST redirects back with an error.

## Settings

Read from environment variables (or a `.env` file) by `internal.config.Settings`.

| Variable | Default | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | `''` | OpenAI settings |

`OPENAI_API_KEY` is a secret: it is read through `get_credential`, so it can come from a systemd credential.

## Data model

The tables mirror the definitions of the platform's chat backend (the models say so in their docstrings); this application manages the rows and ships no migration.

**`SystemPrompt`** maps the `system_prompts` table: `id`, `slug`, `name`, `description`, `required_scopes`, `is_default`, `created_at`, `updated_at`.

**`SystemPromptVersion`** maps the `system_prompt_versions` table: `id`, `prompt_id`, `version`, `content`, `metadata_`, `is_current`, `created_at`.

Versions carry a JSONB `metadata` column (an array/JSONB mapping like the other shared tables).

## Tests

pytest:

- `tests/routes/test_prompts.py`
- `tests/services/test_prompt_generator.py`
- `tests/routes/test_prompts_sidebar.py`

The tests cover each route handler with a mocked session (versioning rules, default prompt, generation redirects, bulk deletes), the generator service and the prompt model helpers. The bulk deletes of prompts and of versions are also tested with the comma-separated selection the pages send.

`tests/routes/test_prompts_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/prompts.feature`):

- List prompts
- List prompts with search filter
- List prompts unauthenticated
- View new prompt form
- Create a prompt
- Create a prompt with duplicate slug
- Create a prompt with invalid metadata JSON
- View generate prompt form when OpenAI configured
- View generate prompt form when OpenAI not configured
- Generate a prompt via AI
- Generate a prompt with short description
- View prompt detail
- View prompt detail not found
- View prompt edit form
- Update a prompt
- Activate a prompt version
- Delete a non-current prompt version
- Cannot delete current prompt version
- Delete a prompt
- Cannot delete the default prompt
- Bulk delete prompts
- Bulk delete versions
- Sidebar on the prompts list
- Sidebar on the new prompt form
- Sidebar on the generate prompt form
- Sidebar on the prompt detail
- Sidebar on the prompt edit form
- Sidebar gated links follow the scopes on the prompts list

The generator is replaced by a mock and the `OpenAI is configured` / `OpenAI is not configured` steps toggle the key for the scenario (they are reused by the knowledge base scenarios); everything else runs against the throw-away SQLite database.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/prompts.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The prompts are listed with their current version
- The Prompts link leads to the list
- A user without the prompt scope gets the access denied page
- An anonymous visitor comes back to the page asked for after the login
- Searching narrows the list
- The list is paginated and keeps the search
- A prompt is created from the form
- A slug already in use is reported on the form
- Metadata that is not JSON is reported on the form
- The character count follows the content
- A prompt is updated and gets a new version
- A prompt that does not exist sends the user back to the list
- The detail of a prompt shows its versions
- An old version is activated after a confirmation
- An old version is deleted after a confirmation
- Selected versions are deleted in bulk
- A prompt is deleted from its page after a confirmation
- A prompt is deleted from its edit form after a confirmation
- Dismissing the confirmation keeps the prompt
- The default prompt cannot be deleted
- Selected prompts are deleted in bulk
- The generate page needs OpenAI
- A prompt is generated and opened in the form for review
- A description that is too short is stopped by the form

Versions are activated and deleted from the detail page, the selection of several prompts or versions is deleted in bulk, and the generated prompt is reviewed in the form it opens.
