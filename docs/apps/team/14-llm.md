# LLM completions

Agents think with a language model. This feature adds `team.services.llm`, a
small layer over the OpenAI and Anthropic SDKs that gives the rest of the
application one way to ask for a chat completion, with optional tool calling,
whatever the provider. It adds no endpoint; the agent runner uses it.

## API

```python
from team.services import ChatResult, ToolCall, get_chat_completion, get_completion

result: ChatResult = await get_chat_completion(
    provider="anthropic",          # "openai" or "anthropic"
    model="claude-sonnet-4-5-20250929",
    system_prompt="You are a developer.",
    messages=[{"role": "user", "content": "Review this."}],
    tools=ToolService().get_tool_definitions(["team_status"]),  # optional
    max_tokens=4096,
)
```

- `get_chat_completion(...)` returns a `ChatResult`: the text `content`, the
  list of `tool_calls` (`ToolCall(id, name, arguments)`) and a `stop_reason`
  that is `end_turn`, `tool_use` (the model wants the tools to run) or
  `max_tokens` (the answer was truncated).
- `get_completion(provider, model, system_prompt, user_message)` returns only
  the text, for simple one-shot requests (1024 tokens at most with Anthropic).
- An unknown provider raises `ValueError("Unsupported provider: <name>")`, and a
  provider whose key is empty raises `ValueError("OPENAI_API_KEY is not
  configured")` or `ValueError("ANTHROPIC_API_KEY is not configured")`.

## Message format

The caller works with one internal format and the module converts it:

- user and assistant messages are `{"role", "content"}`; an assistant message
  that asks for tools also carries `tool_calls`: `[{"id", "name", "arguments"}]`;
- a tool result is `{"role": "tool", "tool_call_id", "content"}`, where the
  content may be a dict;
- tool definitions come in the OpenAI function calling format, as returned by
  the [tool registry](11-tools.md); for Anthropic they are converted to
  `{"name", "description", "input_schema"}`;
- OpenAI receives the system prompt as the first message, tool calls as
  `tool_calls` entries of type `function` and tool results as `tool` messages;
  Anthropic receives it as the `system` field, tool calls as `tool_use` blocks
  and tool results as `tool_result` blocks of a user message.

A fresh SDK client is created for each call and closed afterwards.

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | empty | OpenAI key (declared with the [memory](06-memory.md) feature) |
| `ANTHROPIC_API_KEY` | empty | Anthropic key; read as a credential (see [Foundation](01-foundation.md)) |

## Tests

pytest: `tests/test_services_llm.py` covers both providers (text, tool calls,
truncation, message and tool conversion, missing keys, unsupported provider,
text completions) with mocked SDK clients.

behave (`features/llm.feature`), with fake SDK clients that record the request
and answer with a scripted response:

- OpenAI answers with text
- OpenAI asks to call a tool
- OpenAI reports a truncated answer
- Tool results are sent back to OpenAI in its own format
- Anthropic answers with text
- Anthropic asks to call a tool
- Tool results are sent back to Anthropic in its own format
- A provider needs its API key (outline: openai, anthropic)
- An unknown provider is rejected
- A plain text completion
