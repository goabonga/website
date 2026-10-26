# Event collection

Collection is the write path of the service: websites send events, the service
creates a visitor session on the first request, stores every event and keeps
the session alive with a cookie. It combines the storage layer and the
enrichment services described in the previous pages.

## Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/collect` | POST | Batch of 1 to 100 events as JSON |
| `/collect` | GET | Beacon for clients without JavaScript, answers a 1x1 GIF |

Both endpoints are public: no authentication is required.

### `POST /collect`

```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "events": [
    {
      "event_type": "pageview",
      "page_url": "https://example.com/",
      "page_title": "Home",
      "event_data": {"element": "button"}
    }
  ]
}
```

- `events` is required, with 1 to 100 items; `event_type` (at most 50
  characters) is required for each of them. `user_id` (UUID) is optional and
  is linked to the session when the session has no user yet.
- The answer is `{"success": true, "session_id": "...", "events_count": N}`.
  Invalid payloads are rejected with `422`.

### `GET /collect`

Query parameters: `t` (event type, required), `d` (JSON encoded event data,
silently ignored when it is not valid JSON) and `u` (page URL). The response is
a transparent GIF with `Cache-Control` set from `PIXEL_CACHE_CONTROL`,
`Pragma: no-cache` and `Expires: 0`.

## Sessions

`CollectorService.get_or_create_session` looks the session up by the value of
the session cookie (`ua_sid` by default):

- A known session gets its `last_seen` refreshed and, if it has none yet, the
  `user_id` of the request.
- Otherwise a session is created with a random identifier (or the identifier
  presented by the client) and these attributes: client IP, country and city
  (GeoIP), user agent with device type, browser and OS (see the enrichment
  page), `Referer`, the five `utm_*` query parameters and the landing URL.

For a new session the response sets the cookie `HttpOnly`, with `Max-Age`,
`Secure`, `SameSite` and `Domain` taken from the settings. `SameSite=none`
requires `Secure`, so a plain HTTP test client drops the cookie.

### Client IP

`get_client_ip` takes the first address of `X-Forwarded-For` (set by the
reverse proxy), or the socket address. With `ANONYMIZE_IP=true` the last IPv4
octet is replaced by `0`, and IPv6 addresses are cut to their first 48 bits,
before anything is stored.

Every request also sets the logging context (`sid=`, `ip=`) so log lines can
be correlated.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `SESSION_COOKIE_NAME` | `ua_sid` | Name of the session cookie |
| `SESSION_COOKIE_MAX_AGE` | `31536000` | Cookie lifetime in seconds (one year) |
| `SESSION_COOKIE_SECURE` | `true` | Send the cookie over HTTPS only |
| `SESSION_COOKIE_SAMESITE` | `none` | `lax`, `strict` or `none` |
| `SESSION_COOKIE_DOMAIN` | empty | Cookie domain, for example `.example.com` |
| `PIXEL_CACHE_CONTROL` | `no-cache, no-store, must-revalidate` | `Cache-Control` of the GIF responses |
| `ANONYMIZE_IP` | `false` | Mask the client IP before storing it |

The cookie name is read from the settings when the cookie is set, but the
endpoint reads the incoming cookie from a parameter named `ua_sid`: changing
`SESSION_COOKIE_NAME` changes the cookie that is sent, not the one that is
read back.

## Tests

pytest:

- `test_services_collector.py`: tracking key generation, IP extraction
  (proxy header, socket, IPv4 and IPv6 anonymization), session lookup and
  creation, user linking and event creation, all with a mocked database
  session.
- `test_routes_collect.py`: request models, both endpoints, cookie handling
  and the beacon parameters.
- `test_config.py`: cookie, pixel and anonymization settings.
- `test_main.py`: both routes are registered.

behave (`features/collect.feature`, through the ASGI application and the
temporary SQLite database):

- Collect an event via POST
- Collect several events in one request
- A request without events is rejected
- A new visitor receives a session cookie
- A returning visitor keeps its session
- The beacon returns a transparent GIF and records the event
- The beacon accepts JSON encoded event data
- The beacon ignores event data that is not JSON
- The beacon requires an event type
- Device information is stored with the session
- The client IP comes from the proxy header
- IP anonymization masks the last octet
- UTM parameters are stored with the session
