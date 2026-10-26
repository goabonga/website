# Call handler

The call handler is the feature that turns the previous building blocks
into a working bot. `asterisk.call_handler.handle_call(session)` is
registered as the handler of the AudioSocket server and, for each call,
connects an `OpenAIRealtimeClient`, converts the audio in both directions
and lets the model end the call.

## What it does

For every call `handle_call()`:

1. Creates an `OpenAIRealtimeClient` with the model, voice and system
   prompt from the settings and connects it.
2. Waits 0.3 s, then asks the model to speak first by sending
   `GREETING_MESSAGE` as a user message.
3. **Caller to OpenAI**: the 8 kHz frames received from Asterisk are
   buffered in 640-byte chunks (40 ms), resampled to 24 kHz and sent with
   `send_audio()`.
4. **OpenAI to caller**: the 24 kHz audio deltas are resampled to 8 kHz,
   cut into exact 320-byte frames and queued. A sender loop writes one
   frame every 20 ms to Asterisk and sends a silent frame when the queue
   is empty, so the stream never stalls.
5. **Barge-in**: the OpenAI server-side detection already reports when the
   caller starts speaking. In addition, while the model is responding, a
   local detector computes the RMS of every incoming frame; three
   consecutive frames above 1000 (about 60 ms), at most once every 300 ms,
   cancel the response and clear the buffered output so the old answer
   stops immediately.
6. **Hangup**: when the model calls the `hangup` tool, the handler waits
   (up to 3 s) for the current response to finish, (up to 5 s) for the
   queued audio to play, then 0.5 s more, and sends a hangup packet to
   Asterisk.
7. When the call ends, for any reason, the OpenAI connection is closed.
   Errors are logged and never propagate to the server.

Caller transcripts are logged at `INFO` level. Unknown tool names are
ignored and answered with a generic success.

`asterisk.main` now registers `handle_call` on the server, so
`python -m asterisk.main` answers calls end to end.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | empty | OpenAI API key (secret, required for real calls) |
| `OPENAI_MODEL` | `gpt-4o-realtime-preview-2024-12-17` | Realtime model |
| `OPENAI_VOICE` | `alloy` | Voice used for answers |
| `OPENAI_SYSTEM_PROMPT` | short assistant prompt asking for brief answers in French | System prompt of the session |
| `GREETING_MESSAGE` | `Say hello to the caller, introduce yourself as Chris, and ask how you can help.` | Instruction sent to the model when the call starts |

`OPENAI_API_KEY` is a secret. When `CREDENTIALS_DIRECTORY` is set (systemd
`LoadCredentialEncrypted`), `get_credential()` reads the key from the file
of that name in this directory first and falls back to the environment
otherwise. Use this in production so that the key never appears in an
environment file.

`GREETING_MESSAGE` is read when `asterisk.call_handler` is imported;
the other variables are read by `asterisk.config`.

## Data model

None.

## Tests

Both external sides are faked.

- pytest: `tests/test_call_handler.py` patches `OpenAIRealtimeClient` and
  uses a mocked session; it covers client creation (including the model,
  voice and prompt), greeting, callbacks, the hangup flow and its waits,
  the output frame sender loop, the interruption detector (RMS threshold,
  three-frame rule, debounce) and both audio directions. `tests/test_config.py`
  covers `get_credential` and the OpenAI settings, `tests/test_main.py` the
  handler registration.
- behave: `features/call_handler.feature` runs the real call handler with
  the real `AudioSocketSession` on top of `FakeAsterisk` and the real
  `OpenAIRealtimeClient` on top of `FakeRealtimeSocket`
  (`features/steps/fakes.py`). Scenarios: *The bot speaks first with the
  configured voice and prompt*, *Caller audio is resampled and forwarded
  to OpenAI*, *Model audio is played to the caller in 20 ms frames*,
  *Silence is sent while the model is quiet*, *The caller can interrupt
  the model*, *The model hangs up after saying goodbye* and *The call ends
  when Asterisk hangs up*.
