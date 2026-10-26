# LLM client and tools

The bridge to OpenAI: a thin async client for chat completions and
embeddings, and a registry of "tools" the model may call (OpenAI function
calling), filtered by the caller's scopes.

## OpenAIClient

`OpenAIClient` creates an `AsyncOpenAI` client with `OPENAI_API_KEY` and uses
the model from `OPENAI_MODEL`.

| Method | Behaviour |
|--------|-----------|
| `chat(messages, tools, tool_choice, temperature, max_tokens)` | One completion. Returns `{"content", "role", "tool_calls", "usage"}`; `tool_calls` is `None` or a list of `{"id", "name", "arguments"}` with the JSON arguments already parsed; `usage` holds `prompt_tokens` and `completion_tokens` |
| `stream(messages, temperature, max_tokens)` | Async generator yielding `{"type": "token", "content"}` events and a final `{"type": "usage", ...}` event |
| `get_embedding(text, model)` | One embedding vector |

The token limit is sent as `max_completion_tokens`. The model families `gpt-5`,
`o1`, `o3` and `o4` reject a custom temperature, so it is only sent for
other models. API errors are logged and re-raised.

## Tool registry

`ToolRegistry.register(name, description, parameters, ...)` is a decorator
that records a handler together with its JSON schema. Options:

| Option | Meaning |
|--------|---------|
| `requires_context` | The handler receives a `ToolContext` first (user id, session id, conversation id, authentication flag, access token, scopes) |
| `required_scopes` | The caller must hold all of these scopes; `None` means public |
| `hidden` | Left out of the `help_me` listing |
| `save_in_history` | When `False`, the exchange is not stored in the conversation |

`get_openai_tools(user_scopes)` returns the accessible tools in the OpenAI
format, so the model never even sees a tool it may not use.
`execute(name, arguments, context)` returns a `ToolResult(success, data,
error)`; an unknown tool, a missing scope or an exception in the handler
produce a failed result instead of raising.

### Built-in tools

They are registered on the global `tool_registry` when `backend.llm.tools`
is imported.

| Tool | Role |
|------|------|
| `search_knowledge` | Semantic search of the knowledge base (optional namespace), using the caller's scopes |
| `get_session_info` | Describes the caller; for an authenticated caller it fetches the profile from the issuer's userinfo endpoint |
| `auth_action` | Returns a client-side action (`login`, `logout`, `register`, `account`) for the front end; fails when `OAUTH2_ISSUER` is not configured |
| `new_conversation` | Archives the current conversation so the next message starts a new one; not saved in history |
| `help_me` | Lists the visible tools with example phrases; hidden from its own list |

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_MODEL` | `gpt-4o-mini` | Chat model |

`OPENAI_API_KEY` is described in the knowledge base page.

## Tests

- pytest: `tests/llm/test_client.py` and `tests/llm/test_tools.py`.
- behave: `features/llm_tools.feature` ("Anonymous callers only see public
  tools", "Callers with the scope see the restricted tool", "A public tool
  is executed with the model arguments", "A restricted tool is denied without
  its scope", "An unknown tool is reported", "The built-in tools are
  registered", "Reasoning models use the completion token limit only", "A
  chat completion is normalised"). OpenAI is replaced by a mock client.
