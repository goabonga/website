# OpenAI Realtime client

`asterisk.openai_realtime.OpenAIRealtimeClient` is the WebSocket client
that talks to the OpenAI Realtime API. It streams 24 kHz PCM audio in both
directions, lets the server detect when the caller speaks, and relays tool
calls (function calling) to a callback. It does not know anything about
Asterisk: the call handler feature connects the two sides.

## What it does

- `connect()` opens `wss://api.openai.com/v1/realtime?model=<model>` with
  the headers `Authorization: Bearer <key>` and `OpenAI-Beta: realtime=v1`,
  sends a `session.update` message and starts a background receive loop.
  Connection errors are logged and re-raised.
- The session is configured for text and audio, `pcm16` input and output,
  `whisper-1` transcription of the caller and server-side voice activity
  detection (`threshold` 0.3, 200 ms prefix padding, 400 ms of silence to
  end a turn, response created automatically).
- Tools: the client always declares a `hangup(reason)` function and appends
  the `tools` given to its constructor.
- Sending: `send_audio()` (base64 `input_audio_buffer.append`),
  `commit_audio()`, `send_text()` (user message followed by
  `response.create`) and `cancel_response()` (`response.cancel`). They do
  nothing when the client is not connected.
- Receiving, dispatched by message type:
    - `response.audio.delta` calls the audio callback with decoded PCM.
    - `conversation.item.input_audio_transcription.completed` calls the
      transcript callback.
    - `response.created` / `response.done` / `response.cancelled` maintain
      `is_responding`; `response.done` also calls the response-done
      callback.
    - `input_audio_buffer.speech_started` while the model is responding is
      a barge-in: the client sends `response.cancel` and calls the
      interrupt callback.
    - `response.function_call_arguments.done` calls the tool callback with
      the tool name and parsed arguments. If the callback returns an
      awaitable it is awaited (errors become `{"error": ...}`), then the
      result is sent as a `function_call_output` item, followed by
      `response.create` so the model speaks about it. `hangup` is the
      exception: no new response is requested, and a `None` result is sent
      as `{"success": true}`.
    - `error` messages are logged.
- `disconnect()` stops the receive loop and closes the socket.

Callbacks are registered with `set_audio_callback`,
`set_transcript_callback`, `set_interrupt_callback`,
`set_response_done_callback` and `set_tool_call_callback`.

## Settings

The client takes everything as constructor arguments (`api_key`, `model`,
default `gpt-4o-realtime-preview-2024-12-17`, `voice`, default `alloy`,
`system_prompt`, `tools`). The environment variables that feed them are
introduced with the call handler.

## Data model

None.

## Dependencies

Adds `websockets` to the project dependencies.

## Tests

The OpenAI side is faked: no network connection is ever opened.

- pytest: `tests/test_openai_realtime.py` mocks `websockets.connect` and
  the connection object, and covers connection, session configuration,
  every sender, every message type and the tool call flow.
- behave: `features/openai_realtime.feature` uses `FakeRealtimeSocket`
  (`features/steps/fakes.py`), a scripted WebSocket that records what the
  client sends and feeds it server messages. Scenarios: *Connecting
  configures the session*, *Custom tools are declared next to the hangup
  tool*, *Sending audio*, *Receiving audio*, *Receiving the caller
  transcript*, *Sending a text message asks for a response*, *A tool call
  is answered and a new response requested*, *A hangup tool call does not
  request a new response*, *The caller interrupts the model*, *Response
  state is tracked* and *Disconnecting*.
