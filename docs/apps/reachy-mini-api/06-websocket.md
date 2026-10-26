# WebSocket channel

A bidirectional channel the robot keeps open to receive real-time updates
and to send messages to the other connected clients.

## Endpoint

`WS /ws`. The endpoint is not in the OpenAPI schema and does **not** check a
bearer token: access is restricted by the network (the nginx virtual host
only allows the VPN and the local LAN).

## Protocol

Messages are JSON objects with a `type` field. Every message sent by the
server carries an ISO 8601 UTC `timestamp`.

| Direction | Message | Reply |
| --- | --- | --- |
| server, on connect | | `{"type": "connected", "message": "Connected to Reachy Mini API"}` |
| client | `{"type": "ping"}` | `{"type": "pong"}` |
| client | `{"type": "status"}` | `{"type": "status", "connections": <open connections>}` |
| client | `{"type": "broadcast", "data": {...}}` | every connected client, including the sender, receives `{"type": "broadcast", "data": {...}}` (`data` defaults to `{}`) |
| client | any other `type` (or none) | `{"type": "ack", "received": <the message>}` |
| client | text that is not JSON | `{"type": "error", "message": "Invalid JSON"}`, the connection stays open |

`ConnectionManager` (`reachy_mini_api.main.manager`) keeps the list of open
connections in memory. A failing client is skipped during a broadcast. The
list is local to the process, which is why the deployment runs a single
gunicorn worker.

Connect, every message, broadcast and disconnect are written to the logs as
`ACTION: websocket_connect`, `websocket_message`, `websocket_broadcast` and
`websocket_disconnect` with the client host and a connection id (see
[Dual-stream logging](02-logging.md)).

## Settings

No setting of its own.

## Data model

None. Connections are held in memory only.

## How it is tested

Pytest (`test_websocket.py`): `ConnectionManager` (connect, disconnect,
personal message, broadcast and failing client) and the endpoint through
`TestClient` (welcome, ping, status, broadcast with and without data, ack,
invalid JSON, message without type, two clients, disconnect and audit log).

Behave (`apps/reachy-mini-api/features/websocket.feature`), in-process
through the Starlette test client:

- Connect and receive the welcome message
- Ping returns a pong
- Status reports the open connections
- Broadcast reaches the connected clients
- Broadcast without data uses an empty object
- Unknown message type returns an acknowledgment
- Invalid JSON returns an error
