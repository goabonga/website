# Knowledge base

The knowledge base is the question-and-answer corpus behind the assistant's retrieval-augmented
generation. This last feature adds the entries themselves (stored with a pgvector embedding), an
AI-assisted way to generate them from a source text, and a multi-step validation pipeline that decides
whether an entry is trustworthy enough to be served. Embedding, generation and validation run in a
Celery worker, so this feature introduces the Celery application and its two tasks, and with
them the second process of the deployment.

## What it adds

| Module | Role |
| --- | --- |
| `internal/celery.py` | Celery application configuration. |
| `internal/schemas/__init__.py` | Pydantic schemas for request/response validation. |
| `internal/schemas/validation.py` | Pydantic schemas for the knowledge validation pipeline. |
| `internal/services/embeddings.py` | Embedding generation service using OpenAI. |
| `internal/services/embeddings_sync.py` | Sync embedding generation service using OpenAI. |
| `internal/services/knowledge_generator.py` | AI-powered knowledge entry generation service using OpenAI. |
| `internal/services/knowledge_generator_sync.py` | Sync AI-powered knowledge entry generation service using OpenAI. |
| `internal/services/knowledge_validation.py` | Knowledge validation pipeline orchestrator. |
| `internal/services/validators/__init__.py` | Knowledge validation pipeline validators. |
| `internal/services/validators/cleaning_validator.py` | Cleaning & normalization: HTML removal, log/stack trace detection, language detection, UTF-8. |
| `internal/services/validators/decision_engine.py` | Decision engine: aggregate step results into a final ACCEPT/REJECT/NEEDS_REVIEW. |
| `internal/services/validators/dedup_validator.py` | Deduplication: embedding similarity check against existing entries. |
| `internal/services/validators/length_validator.py` | Answer length validation: token count bounds on answer field. |
| `internal/services/validators/quality_validator.py` | RAG quality scoring: heuristic scoring to filter low-signal content. |
| `internal/services/validators/retrievability_validator.py` | Retrievability test: generate candidate questions, verify the chunk is searchable. |
| `internal/services/validators/schema_validator.py` | Schema validation: required fields, type checks, content guards. |
| `internal/services/validators/semantic_validator.py` | Semantic validation: LLM classifier to judge knowledge base utility. |
| `internal/tasks/__init__.py` | Celery tasks package. |
| `internal/tasks/knowledge_generation.py` | Celery task for asynchronous knowledge generation. |
| `internal/tasks/knowledge_validation.py` | Celery task for asynchronous knowledge validation. |
| `internal/routes/knowledge.py` | Knowledge Base CRUD routes for RAG management. |

It also ships 5 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /knowledge | `knowledge:read` | List all knowledge entries with pagination, search, namespace and status filter. |
| GET | /knowledge/new | `knowledge:write` | Show form to create a new knowledge entry. |
| GET | /knowledge/generate | `knowledge:write` | Show form to generate knowledge entries using AI. |
| POST | /knowledge/generate | `knowledge:write` | Dispatch async knowledge generation task. |
| GET | /knowledge/generate/status/{task_id} | `knowledge:read` | Poll generation task status. |
| POST | /knowledge/new | `knowledge:write` | Create a new knowledge entry with embedding. |
| GET | /knowledge/{entry_id} | `knowledge:read` | View knowledge entry detail. |
| GET | /knowledge/{entry_id}/edit | `knowledge:write` | Show form to edit a knowledge entry. |
| POST | /knowledge/{entry_id}/edit | `knowledge:write` | Update a knowledge entry with new embedding if question changed. |
| POST | /knowledge/{entry_id}/regenerate-embedding | `knowledge:write` | Regenerate embedding for an existing entry. |
| GET | /knowledge/{entry_id}/validation | `knowledge:read` | View validation details for a knowledge entry. |
| POST | /knowledge/{entry_id}/revalidate | `knowledge:write` | Re-trigger validation for an entry. |
| POST | /knowledge/{entry_id}/approve | `knowledge:write` | Manually approve a NEEDS_REVIEW or REJECTED entry. |
| POST | /knowledge/{entry_id}/reject | `knowledge:write` | Manually reject an entry. |
| POST | /knowledge/{entry_id}/delete | `knowledge:delete` | Delete a knowledge entry. |
| POST | /knowledge/bulk-delete | `knowledge:delete` | Delete multiple knowledge entries. |

The list and detail pages request the whole `knowledge` resource plus `vpn:admin` and `billing:read` (navigation). `internal:*` grants all knowledge scopes.

## Entries

- **List** (`/knowledge`): paginated, searchable, filterable by namespace and by status.
- **Create and edit** (`/knowledge/new`, `/knowledge/{id}/edit`): a question, an answer, a namespace and
  metadata. When `OPENAI_API_KEY` is set the question is embedded (`RAG_EMBEDDING_MODEL`) on creation,
  and again when the question changes; `POST /knowledge/{id}/regenerate-embedding` recomputes it on demand.
  Without a key entries are saved without an embedding.
- **Status**: a new entry is `pending` when validation is enabled (`VALIDATION_ENABLED`, default on) and a validation
  task is queued; otherwise it is `accepted` immediately. The other states are `validating`, `rejected` and
  `needs_review`.
- **Manual decision**: `approve` accepts an entry in `needs_review` or `rejected`, `reject` rejects it,
  and `revalidate` queues the pipeline again. The detail of the last run is at `/knowledge/{id}/validation`.
- **Delete** (single and bulk): needs `knowledge:delete`. A form cannot be nested in another one, so the Delete button of an edit form carries its own `formaction` and confirmation: nested, the browser would drop the inner form and the button would save the page instead. A failed save redirects back to the form with an `error` message, which the form shows.

## AI generation

`/knowledge/generate` takes a source text (at least 50 characters), a namespace, a number of entries (1 to 50)
and optional context. The POST does not wait for the model: it queues
`internal.tasks.knowledge_generation.generate_knowledge_entries` and answers with the Celery task id as JSON; the
page polls `GET /knowledge/generate/status/{task_id}` (state, progress step and, once finished, the
number of created entries and the namespace to jump to). The task asks OpenAI for question-answer pairs
(`internal.services.knowledge_generator_sync`), embeds each question, stores the entries in the chosen namespace
(falling back to `general`) and queues one validation task per entry when validation is enabled. It retries up to three
times, a minute apart. An unconfigured OpenAI key answers `400`.

## Validation pipeline

`internal.services.knowledge_validation.KnowledgeValidationService` runs, in a worker with a synchronous
session, the steps below on an entry and stores the verdict and the details of every step in
`validation_details`:

| Step | What it checks |
| --- | --- |
| `schema` | required fields, minimum length, no binary content |
| `cleaning` | strips HTML, detects logs and stack traces, detects the language; the cleaned text feeds the next steps |
| `quality` | heuristic RAG-quality score against `VALIDATION_QUALITY_MIN_SCORE` |
| `semantic` | an LLM (`VALIDATION_SEMANTIC_MODEL`) judges whether the entry is useful, with a confidence threshold |
| `dedup` | cosine similarity of the question's embedding with the existing entries (`VALIDATION_DEDUP_SIMILARITY_THRESHOLD`) |
| `length` | the answer's token count between the configured bounds |
| `retrievability` | generates candidate questions and checks that the entry is found among the top results |

A `schema` or `dedup` rejection is final and stops the pipeline. Otherwise the decision engine counts the step
verdicts: two or more rejections reject the entry, one rejection or any "needs review" sends it to a human, and
all-clear accepts it. The `dedup` and `retrievability` steps issue pgvector SQL, so they need PostgreSQL with the
`vector` extension; their unit tests mock the database session.

## Celery application

`internal.celery.celery_app` uses `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` (both default to
`REDIS_URL`), JSON serialisation, UTC, the default queue `internal`, `task_acks_late` and a prefetch multiplier of 1.
A worker is started with:

```bash
uv run --package internal celery -A internal.celery:celery_app worker -Q internal --loglevel=info
```

No periodic task is defined, so no beat process is needed.

## Settings

Read from environment variables (or a `.env` file) by `internal.config.Settings`.

| Variable | Default | Notes |
| --- | --- | --- |
| `CELERY_BROKER_URL` | `''` | Celery |
| `CELERY_RESULT_BACKEND` | `''` | Celery |
| `RAG_EMBEDDING_MODEL` | `'text-embedding-3-small'` | OpenAI settings |
| `VALIDATION_ENABLED` | `True` | Knowledge validation pipeline |
| `VALIDATION_QUALITY_MIN_SCORE` | `0.4` | Knowledge validation pipeline |
| `VALIDATION_DEDUP_SIMILARITY_THRESHOLD` | `0.92` | Knowledge validation pipeline |
| `VALIDATION_ANSWER_MIN_TOKENS` | `30` | Knowledge validation pipeline |
| `VALIDATION_ANSWER_MAX_TOKENS` | `800` | Knowledge validation pipeline |
| `VALIDATION_ANSWER_WARN_MIN_TOKENS` | `50` | Knowledge validation pipeline |
| `VALIDATION_ANSWER_WARN_MAX_TOKENS` | `600` | Knowledge validation pipeline |
| `VALIDATION_SEMANTIC_MODEL` | `'gpt-4o-mini'` | Knowledge validation pipeline |
| `VALIDATION_SEMANTIC_CONFIDENCE_THRESHOLD` | `0.7` | Knowledge validation pipeline |
| `VALIDATION_RETRIEVABILITY_MIN_HITS` | `1` | Knowledge validation pipeline |

`OPENAI_API_KEY` (from the prompts feature) enables embeddings and generation; the `VALIDATION_*` variables tune the
pipeline thresholds (token bounds, minimum quality score, similarity threshold, semantic confidence, retrievability hits).

## Tests

pytest:

- `tests/routes/test_knowledge.py`
- `tests/tasks/test_knowledge_generation_task.py`
- `tests/tasks/test_knowledge_validation_task.py`
- `tests/services/test_embeddings.py`
- `tests/services/test_embeddings_sync.py`
- `tests/services/test_knowledge_generator.py`
- `tests/services/test_knowledge_generator_sync.py`
- `tests/services/test_knowledge_validation.py`
- `tests/services/test_cleaning_validator.py`
- `tests/services/test_decision_engine.py`
- `tests/services/test_dedup_validator.py`
- `tests/services/test_length_validator.py`
- `tests/services/test_quality_validator.py`
- `tests/services/test_retrievability_validator.py`
- `tests/services/test_schema_validator.py`
- `tests/services/test_semantic_validator.py`
- `tests/routes/test_knowledge_sidebar.py`
- `tests/routes/test_sidebar.py`

The tests cover the route handlers, both Celery tasks (including retries and the dispatch of validation tasks), the embedding and

`tests/routes/test_knowledge_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user. `tests/routes/test_sidebar.py` runs every page of the application against the whole scope matrix and fails when an HTML route is not registered for the sidebar tests.
generator services (async and sync), the validation service and every validator with the OpenAI client and the database mocked.
The OpenAI clients are patched where the sync services are constructed, so no API key is needed.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/knowledge.feature`):

- List knowledge entries when empty
- List knowledge entries with data
- List knowledge entries with search filter
- List knowledge entries filtered by namespace
- List knowledge entries unauthenticated
- View new knowledge entry form
- Create a knowledge entry
- Create a knowledge entry with invalid metadata JSON
- View generate knowledge form when OpenAI configured
- View generate knowledge form when OpenAI not configured
- Generate knowledge entries dispatches async task
- Poll generation task status returns SUCCESS
- View knowledge entry detail
- View knowledge entry detail not found
- View knowledge entry edit form
- Update a knowledge entry
- Delete a knowledge entry
- Bulk delete knowledge entries
- Bulk delete with empty list
- Sidebar on the knowledge list
- Sidebar on the new knowledge entry form
- Sidebar on the generate knowledge form
- Sidebar on the knowledge entry detail
- Sidebar on the knowledge entry edit form
- Sidebar on the knowledge entry validation
- Sidebar gated links follow the scopes on the knowledge list
- A super administrator sees every section
- A user without the VPN and billing scopes does not see them
- Gated links follow the scopes
- The active link follows the page

The sidebar scenarios reuse the steps of `features/steps/sidebar_steps.py`. `features/sidebar.feature` checks the complete link set per scope and the active link on pages that need no data.

Scenarios run against the throw-away SQLite database with the embedding service, the generator and the Celery
`delay` / `AsyncResult` calls mocked, so no Redis, worker or OpenAI access is needed. The pgvector-specific SQL of the
validators is covered by the pytest unit tests only.

Browser scenarios, run in Chromium against the application served on a local socket (`uv run --package internal --group dev behave apps/internal/features -t @browser`):

`features/browser/knowledge.feature`:

- The entries are listed with their namespace and status
- The Knowledge Base link leads to the list
- A user without the knowledge scope gets the access denied page
- A user who may only read cannot create an entry
- An anonymous visitor comes back to the page asked for after the login
- Searching narrows the list
- The entries are filtered by status and namespace
- The list is paginated and keeps the search
- An entry is created from the form and sent to validation
- The embedding of a new entry is generated when OpenAI is configured
- Metadata that is not JSON is reported on the form
- The form requires a question and an answer
- An entry is updated from its edit form
- Metadata that is not JSON is reported on the edit form
- An entry that does not exist sends the user back to the list
- The detail of an entry shows its status
- The validation details of an entry are shown
- An entry is validated again
- An entry is rejected and then approved
- The embedding of an entry is regenerated
- Regenerating the embedding is not offered without OpenAI
- An entry is deleted from its page after a confirmation
- An entry is deleted from its edit form after a confirmation
- Dismissing the confirmation keeps the entry
- Selected entries are deleted in bulk
- The generate page needs OpenAI
- Entries are generated in the background and the list is shown when they are ready
- A text that is too short is stopped by the form
- A generation that fails is reported

`features/browser/sidebar.feature`:

- A super administrator sees every section
- A user without the VPN and billing scopes does not see them
- The gated links follow the scopes of the user
- The exchange asks for the scopes of the page and of the sidebar
- The exchange grants the sidebar scopes the user holds
- The highlighted link follows the page
- Every link of the sidebar leads to its section
- A user holding only the scopes of the sidebar is refused the pages of the sections
- A user without the scope of a section is refused its pages
- A user holding no scope at all is refused
- The user is shown in the sidebar and signs out from it
- On a narrow screen the sidebar is a menu that opens

The generation of entries runs through its JavaScript: the form is sent in the background, the page polls the task and shows the list when it succeeded. `features/browser/sidebar.feature` proves the sidebar across all pages against the real token exchange of the provider: the links by scope, the highlighted section of every kind of page, the scopes the exchange asked for and was granted, the pages refused to a user who only holds the scopes of the sidebar, and the menu of a narrow screen.
