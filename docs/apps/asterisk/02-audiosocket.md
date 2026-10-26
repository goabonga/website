# AudioSocket server

The AudioSocket server is the telephony side of the bot. Asterisk opens a
TCP connection to the daemon for every call (dialplan `AudioSocket()`
application) and both ends exchange small typed packets carrying the
call identity and 8 kHz audio.

From this feature on, `python -m asterisk.main` starts the server and
serves until it receives `SIGTERM` or `SIGINT`. No call handler is
registered yet, so an accepted connection only logs a warning and is
closed; the call handler feature plugs the bot in.

## What it does

- `AudioSocketServer(host, port)` listens with `asyncio.start_server` and
  creates one `AudioSocketSession` per connection. The handler registered
  with `set_handler()` is awaited with that session; the connection is
  always closed afterwards.
- `AudioSocketSession` wraps the stream reader and writer of a call:
    - `receive_loop()` reads packets until hangup, error or end of stream,
      storing the channel UUID and passing caller audio to the callback
      registered with `set_audio_callback()`.
    - `send_audio_frame(frame)` writes exactly one 320-byte frame (20 ms
      of 8 kHz, 16-bit mono PCM), padding short frames with zeros and
      truncating long ones.
    - `send_audio(data)` splits a buffer into padded 320-byte frames.
    - `send_hangup()` tells Asterisk to end the call.
    - `is_active` becomes `False` on hangup, error, dropped connection or
      `close()`.
- `main()` installs `SIGTERM`/`SIGINT` handlers that stop the server
  gracefully (`shutdown()`).

### Wire format

Each packet is a 3-byte header (1 byte type, 2 bytes big-endian payload
length) followed by the payload.

| Type | Constant | Direction | Payload |
| --- | --- | --- | --- |
| `0x00` | `PACKET_HANGUP` | both | none |
| `0x01` | `PACKET_UUID` | Asterisk to bot | 16-byte channel UUID |
| `0x02` | `PACKET_SILENCE` | Asterisk to bot | none, ignored |
| `0x10` | `PACKET_AUDIO` | both | signed 16-bit little-endian PCM, 8 kHz mono |
| `0xFF` | `PACKET_ERROR` | Asterisk to bot | error text |

An unknown type is logged as a warning and skipped.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `AUDIOSOCKET_HOST` | `127.0.0.1` | Bind address (introduced by the foundation) |
| `AUDIOSOCKET_PORT` | `9092` | TCP port (introduced by the foundation) |

Keep the server on the loopback interface: the protocol has no
authentication.

## Dialplan

Asterisk must route calls to the daemon with the `AudioSocket()`
application, UUID first:

```ini
[audiosocket-bot]
exten => s,1,NoOp(Starting AudioSocket bot)
 same => n,Answer()
 same => n,AudioSocket(${UUID()},127.0.0.1:9092)
 same => n,Hangup()
```

## Data model

None.

## Tests

The Asterisk side is faked: pytest uses mocked stream readers and writers,
behave uses a `FakeAsterisk` object backed by an `asyncio.StreamReader`
and a recording writer (`features/steps/fakes.py`).

- pytest: `tests/test_audiosocket.py` (packet constants, packet reading,
  frame padding and truncation, hangup, every packet type in the receive
  loop, server start and stop) and the `shutdown`/`main` classes of
  `tests/test_main.py`.
- behave: `features/audiosocket.feature`, including *The server hands an
  accepted connection to its handler* (the only scenario that opens a
  socket, on an ephemeral loopback port), *The channel UUID is parsed*,
  *Caller audio is passed to the audio callback*, *A short audio frame is
  padded to 320 bytes*, *Audio is split into 20 ms frames*, *Hangup from
  Asterisk ends the session*, *An error packet ends the session*, *A
  dropped connection ends the session quietly* and *The bot hangs up the
  call*.
