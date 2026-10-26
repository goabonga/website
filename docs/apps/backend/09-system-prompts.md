# Scoped system prompts

The system prompt that frames the assistant is stored in PostgreSQL,
versioned, and chosen per caller from the OAuth2 scopes. The selected text
is cached in Redis.

## Data model

| Table | Model | Columns |
|-------|-------|---------|
| `system_prompts` | `SystemPrompt` | `id`, `slug` (unique), `name`, `description`, `required_scopes` (array), `is_default`, `created_at`, `updated_at` |
| `system_prompt_versions` | `SystemPromptVersion` | `id`, `prompt_id` (foreign key, cascade delete), `version`, `content`, `metadata`, `is_current`, `created_at` |

Content is never edited in place: a change creates a new version and the
`is_current` flag selects the active one. A prompt is accessible when it is
the default prompt, when it has no required scopes, or when the caller holds
all of its required scopes. Its specificity is its number of required scopes.

## PromptService

`PromptService(session)`:

| Method | Behaviour |
|--------|-----------|
| `get_prompt_for_scopes(user_scopes)` | Return the prompt text for a caller (see below) |
| `get_prompt_by_slug(slug)`, `get_default_prompt()` | Read prompts |
| `create_prompt(slug, name, content, ...)` | Create a prompt with its first version |
| `create_version(...)` | Add a version to a prompt |
| `set_current_version(version_id)`, `rollback_to_version(version_id)` | Make a version the current one (rollback is the same operation) |
| `list_versions(prompt_id)`, `list_prompts(...)` | History and scope-filtered listing |

Selection in `get_prompt_for_scopes`:

1. Return the cached text for this scope set when there is one.
2. Load all prompts, keep the accessible ones and pick the non-default prompt
   with the most required scopes; otherwise the default prompt.
3. Use the content of its current version and cache it.
4. Any problem (no prompt, no current version, database error) returns
   `DEFAULT_FALLBACK_PROMPT`, a generic helpful-assistant text built into the
   code. The fallback is not cached.

Anonymous callers pass `None` and therefore only see prompts without
required scopes.

## PromptCache

`prompt_cache` is a process-wide singleton using the Redis database
`PROMPT_CACHE_REDIS_URL`.

| Key | Content |
|-----|---------|
| `prompt:slug:<slug>` | Content of one prompt |
| `prompt:scope:<sorted scopes joined by ':'>` | Selected content for a scope set (`__anonymous__` when empty) |
| `prompt:default` | Content of the default prompt |

Entries expire after `PROMPT_CACHE_TTL` seconds (`0` or less means no
expiry). `invalidate(slug)` removes a slug and every scope entry;
`invalidate()` and `clear()` remove everything. Redis errors are logged and
never raised, so a Redis outage only costs database reads.

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMPT_CACHE_REDIS_URL` | `redis://localhost:6379/4` | Redis database of the prompt cache |
| `PROMPT_CACHE_TTL` | `300` | Cache lifetime in seconds |

## Tests

- pytest: `tests/prompts/test_service.py`, `tests/prompts/test_cache.py`,
  `tests/models/test_prompt.py`.
- behave: `features/prompts.feature` ("Anonymous visitors get the default
  prompt", "A user without the scopes gets the default prompt", "A user with
  the scope gets the matching prompt", "The most specific prompt wins",
  "The selected prompt is cached", "A cached prompt avoids the database",
  "The built-in prompt is used when no prompt exists"). The prompts are built
  in memory and the cache is mocked.
