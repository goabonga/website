# Server-side analytics

When an analytics service is configured, the server reports every page view to
it. The events use the same format as the browser SDK of the
[web client](03-web-client.md), so both sides feed the same collection
endpoint.

## Behaviour

- `frontend.analytics.AnalyticsTracker` queues events and posts each one as a
  JSON document to `<ANALYTICS_URL>/collect` (a trailing slash on the URL is
  ignored):

  ```json
  {"events": [{"event_type": "page_view_server", "page_url": "/pricing"}],
   "ip_address": "203.0.113.7"}
  ```

  `user_id` and `session_id` are added when known, `event_data` is nested in
  the event when given.
- The queue is flushed immediately when it holds 10 events, otherwise 5
  seconds after the first queued event. Deliveries use an `httpx` client with a
  5 second timeout.
- Delivery errors (connection errors and HTTP status 400 and above) are logged
  as warnings and the event is dropped. They never reach the visitor.
- A middleware tracks every request except those whose path starts with
  `/static`. The event type is `page_view_server`; the page URL is the request
  path (no query string). Requests handled by the middleware include the
  health check.
- The client address is the first value of `X-Forwarded-For`, otherwise
  `X-Real-IP`, otherwise the socket peer (`get_client_ip`). It is only
  trustworthy behind a reverse proxy that sets these headers.
- Nothing is sent, and nothing is queued, when `ANALYTICS_URL` is empty.
- When the application stops, the lifespan handler calls `close()`, which
  cancels the delayed flush and delivers the events still queued. Events
  queued after a crash are lost.

## Code

Each application built by `create_app` owns its tracker, available as
`app.state.analytics`. `create_app` accepts an optional `analytics_transport`
(an `httpx.AsyncBaseTransport`) that replaces the network, which is how the
tests and scenarios receive events without any service.

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ANALYTICS_URL` | empty | Base URL of the analytics service. The same value is injected in the page for the browser SDK ([SPA serving](04-spa-serving.md)); empty disables tracking on both sides. |

The `httpx` library is a runtime dependency of the application.

## Tests

pytest (`tests/test_analytics.py`): disabled tracker, endpoint building,
payload shape, HTTP and transport errors, immediate and delayed flush, closing
with a pending flush, client address resolution, the middleware (page views,
static files skipped, nothing sent when unconfigured, failures hidden from the
response), flush on shutdown and one tracker per application.

behave (`features/analytics.feature`, steps in
`features/steps/analytics_steps.py`, which provide an in-memory analytics
service):

- A page view is reported once the application stops
- Static files are not tracked
- The client address comes from the forwarding headers
- Events are posted to the collect endpoint of the service
- Nothing is reported when no analytics service is configured
- A failing analytics service does not affect the responses

`features/environment.py` runs the application as a context manager for each
scenario, so "the application stops" triggers the shutdown flush.

browser (`features/browser/analytics.feature`, tag `@browser`, see [Browser
testing](../../testing/index.md); steps in
`features/steps/browser_analytics_steps.py`, which provide an analytics
service that listens on a real socket and accepts the cross-origin requests of
the web client): the site is browsed in Chromium and the events arrive over
HTTP.

- Page views are reported to the analytics service (delivered when the running
  application stops)
- Static files are not reported (the web client is built and loaded)
- The web client reports the page view itself (tag `@cross-origin`: the
  scenario is not guarded against third-party requests, because Playwright's
  request routing would prevent the preflight of the web client's credentialed
  request)
