# Provisioning status and events

Provisioning takes minutes, so a client needs a way to follow it. This feature
adds three read-only endpoints on a domain: a status snapshot to poll, a
server-sent events (SSE) stream for live updates and the recent event history.
The events themselves are produced by the Celery tasks of the DNS verification
and SSL provisioning features and travel through Redis.

It also adds the `ProvisioningStep` enum (`dns_check`, `nginx_http`, `certbot`,
`nginx_https`).

All endpoints need the `custom-domain:read` scope and follow the same rules as
the domain API: own client only (unless the administration scope, `ADMIN_SCOPE`,
is present) and the caller's client must be registered and active, checked on
every request (`403 Client not authorized` otherwise). Unlike the other domain
endpoints they also find soft-deleted domains.

## Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/domains/{id}/status` | GET | Status snapshot with progress. |
| `/api/v1/domains/{id}/events` | GET | SSE stream of live events. |
| `/api/v1/domains/{id}/events/history` | GET | Recent events, newest first. Query: `limit` (default 50, at most `EVENT_HISTORY_SIZE` are returned) and `since` (ISO 8601 date-time). |

### Status snapshot

`{id, domain, status, progress, last_event, error, retry_count,
next_retry_at}`. The `progress` object is derived from the status only:

| Status | Percentage | Current step | Completed steps |
| --- | --- | --- | --- |
| `pending` | 0 | none | none |
| `dns_verifying` | 10 | `dns_check` | none |
| `dns_verified` | 25 | none | `dns_check` |
| `ssl_provisioning` | 60 | `certbot` | `dns_check`, `nginx_http` |
| `active` | 100 | none | all four |
| `failed`, `suspended`, `expired`, `deprovisioning` | 0 | none | none |

`steps_remaining` lists the other steps. `error` is the domain's
`error_message`. `last_event` and `next_retry_at` are always `null`: the
snapshot does not read the event history.

### Event stream

The stream starts with an `initial_state` event (`domain`, `status`,
`progress`, `timestamp`). If the domain is already `active` or `failed` it then
sends a final `completed` or `error` event and closes. Otherwise it subscribes
to the Redis channel `domain:<id>:events` (polling it every
`SSE_POLL_INTERVAL_SECONDS`) and relays every event under its own type (`status_change`, `step_started`, `step_completed`, `step_failed`,
`completed`, `error`) with the event payload as data, until a `completed` or
`error` event arrives or the client disconnects. A `heartbeat` event with a
timestamp is sent every `SSE_HEARTBEAT_INTERVAL` seconds. The response carries
`Cache-Control: no-cache` and `X-Accel-Buffering: no` so that nginx does not
buffer it.

```text
event: initial_state
data: {"domain": "shop.example.com", "status": "ssl_provisioning", "progress": {...}, "timestamp": "..."}

event: step_completed
data: {"step": "certbot", "message": "SSL certificate obtained successfully", "timestamp": "..."}
```

### History

Reads the Redis list `domain:<id>:event_history` that the tasks maintain (the
`EVENT_HISTORY_SIZE` most recent events, expiring `EVENT_HISTORY_TTL_SECONDS`
after the last event). Each item is
`{type, step, message, timestamp}`; `since` drops older events. The response
also tells whether more events exist than were returned (`has_more`) and the
timestamp of the oldest returned event (`oldest_timestamp`).

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `SSE_HEARTBEAT_INTERVAL` | `30` | Seconds between two `heartbeat` events. |
| `SSE_POLL_INTERVAL_SECONDS` | `1.0` | How often the stream looks for a new message. |
| `EVENT_HISTORY_SIZE` | `100` | Events kept per domain (SSL provisioning page); also the largest `limit` of the history endpoint. |
| `REDIS_URL` | `redis://localhost:6379/13` | Redis holding the channel and the history list. |

## How it is tested

- pytest: `test_routes_events.py` (progress mapping, status endpoint, stream
  and history at HTTP level), `test_routes_events_unit.py` (ownership, history
  parsing, the stream generator consumed event by event, non-terminal messages,
  the remaining statuses and a round trip between the task's event format and
  the history endpoint), `test_routes_events_access.py` (registry check, history
  limit, progress while deleting), the event classes of `test_schemas.py` and the
  `ProvisioningStep` tests of `test_models.py`.
- behave: `features/provisioning_events.feature` covers the progress of pending,
  active and waiting domains, access to another client's domain, reading and
  filtering the history, streaming an already completed domain and streaming
  live events until completion, a deactivated client and a domain being
  deleted. Redis is replaced by an in-process fake that
  replays a fixed list of messages.
