# Chat orchestration and streaming

`ChatOrchestrator` turns a user message into an answer: it lets the model
decide whether a tool is needed, runs the tools, then generates the final
reply with the right context. `stream_chat_response` converts the resulting
events into Server-Sent Events.

## Pipeline

`ChatOrchestrator(session)` builds an `OpenAIClient`, a `ChatService`, a
`KnowledgeBase` and a `PromptService`.

1. **Conversation.** The streaming entry point
   `process_message_stream(message, user_id, session_id, access_token,
   user_scopes)` gets or creates the single active conversation of the owner
   and loads up to 20 history messages.
2. **System prompt.** `PromptService.get_prompt_for_scopes(user_scopes)`
   selects the persona prompt.
3. **Tools.** The accessible tools (see the LLM page) are sent to the model
   with `tool_choice="auto"` and a dedicated tool-use system prompt. The
   `search_knowledge` definition is enriched with the namespaces the caller can
   reach. Every tool call returned by the model is executed through the
   registry.
4. **Answer.** With tool results, the final prompt contains them as factual
   context; without, the model answers with the persona prompt alone. A
   stored conversation summary is added when present. The answer is streamed.
5. **Persistence.** The user message and the assistant answer are saved in
   the conversation. If every executed tool is marked `save_in_history=False`
   (for example `new_conversation`) nothing is saved.
6. **Title and summary.** After the answer, a background task generates a
   conversation title after the first exchange and then every 5 user
   messages, and a summary every 3 user messages (`TITLE_UPDATE_INTERVAL`,
   `SUMMARY_UPDATE_INTERVAL`).

`process_message` is the non-streaming variant; it returns a dictionary with
`content`, `conversation_id`, `intent`, `usage` and `tool_results`.

### Events

The orchestrator yields dictionaries in this order:

| Event | Content |
|-------|---------|
| `history` | Messages loaded before the new one |
| `intent` | `tool_call` when tools ran, `no_match` otherwise |
| `tools` | Tool results (only with `tool_call`) |
| `token` | One piece of the answer |
| `done` | `conversation_id` and the token `usage` |

## Server-Sent Events

`stream_chat_response(generator)` writes `event: <name>` and `data: <json>`
frames for the `intent`, `tools`, `rag`, `token` and `done` events and ends
with an `error` event if the generator raises. The `history` event is
internal and is not forwarded to the client. The `rag` frame (a count) is
supported by the formatter but the orchestrator does not currently produce
it: knowledge base lookups go through the `search_knowledge` tool and appear
in the `tools` event.

## Tests

- pytest: `tests/chat/test_orchestrator.py` and `tests/chat/test_stream.py`.
- behave: `features/chat_orchestration.feature` ("A message without a
  matching tool is answered by the persona", "A tool result is added to the
  model context", "Token usage is reported in the final event", "Events are
  formatted as Server-Sent Events", "A failure is reported as an error
  event"). The model client, chat service, knowledge base and prompt service
  are mocks; the token stream is a fake generator.
