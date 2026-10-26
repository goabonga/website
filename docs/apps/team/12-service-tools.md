# Service tools

Agents can use the other services of the platform. This feature adds the tools
that call the billing, mailler, analytics and auth services, and a generic tool
for any internal service. Like all tools they are registered in the
[tool registry](11-tools.md), so they appear in `GET /platform/tools`, and they
return an `{"error": ...}` object instead of raising when a call fails.

## How a call is made

For every service the base URL is resolved in this order:

1. the agent's `config.credentials` (`billing_base_url`, `mailler_base_url`,
   `analytics_base_url`, `auth_base_url`, `services_base_url`);
2. the global setting of the same name.

When no URL is found the tool answers `"<Service> base URL not configured"`.
The base URL is either a regular HTTP URL, in which case the shared HTTP client
of the tool service is used, or a `unix://` URL pointing to a Unix socket (the
services of the platform run on the same host and listen on sockets), in which
case a dedicated client with a Unix socket transport is created for the call
and closed afterwards (`team.services.tools._http.get_service_client`).

The request is authenticated with `Authorization: Bearer <token>`, where the
token is the agent credential `billing_token`, `mailler_token`,
`analytics_token` or `auth_token` of the service, or, when the agent has none,
the OAuth2 client secret of the application. A non-successful answer of a
service becomes `"<Service> API error <status>: <first 500 characters of the
body>"`.

## Tools provided

| Tool | Request made |
|------|--------------|
| `service_call` | any `method` on `<services base URL>/<service>/<endpoint>` with an optional JSON `body` and extra `headers`; the agent credential `services_api_key` is sent as bearer token; returns the status code and the first 4000 characters of the body |
| `billing_list_subscriptions` | `GET /platform/{saas_id}/subscriptions` with optional `status` and `limit` |
| `billing_get_customer` | `GET /platform/{saas_id}/customers/{customer_id}` |
| `billing_get_subscription` | `GET /platform/{saas_id}/subscriptions/{subscription_id}` |
| `billing_report_usage` | `POST /usage/{saas_id}/report` with `subscription_id`, `quantity` and an optional `action` |
| `mailler_send_email` | `POST /api/v1/send` with `to_email`, `subject`, `html_content` and the optional `text_content`, `from_email` and `provider` |
| `mailler_get_stats` | `GET /api/v1/stats` with optional dates and provider |
| `mailler_list_templates` | `GET /api/v1/templates` |
| `mailler_start_campaign` | `POST /api/v1/campaigns/{campaign_id}/send` |
| `analytics_overview` | `GET /api/v1/stats/overview` with `days` |
| `analytics_pages` | `GET /api/v1/stats/pages` with `days` and a limit |
| `analytics_campaigns` | `GET /api/v1/stats/campaigns` with an inactive filter and a limit |
| `auth_list_users` | `GET /admin/api/users` with `search`, `limit`, `offset` and `is_active` |
| `auth_list_clients` | `GET /admin/api/clients` with `search`, `limit` and `offset` |
| `auth_list_roles` | `GET /admin/api/roles` with `search`, `limit` and `offset` |

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICES_BASE_URL` | empty | Base URL of `service_call` |
| `BILLING_BASE_URL` | empty | Billing service |
| `MAILLER_BASE_URL` | empty | Mailler service |
| `ANALYTICS_BASE_URL` | empty | Analytics service |
| `AUTH_BASE_URL` | empty | Auth service |

Each accepts `http://host` or `unix:///path/to/service.sock`. None is a
secret; the tokens are the agent credentials or `OAUTH2_CLIENT_SECRET` (see
[OAuth2 authentication](02-authentication.md)).

## Tests

pytest: `tests/test_tools_http_helper.py` (HTTP and Unix socket clients),
`tests/test_tools_service_call.py`, `tests/test_tools_billing_ops.py`,
`tests/test_tools_mailler_ops.py`, `tests/test_tools_analytics_ops.py` and
`tests/test_tools_auth_ops.py` (URL and token resolution, request shape,
success, API errors and unconfigured services), and the registry test lists the
new tools.

behave (`features/service_tools.feature`), with an HTTP transport that records
the requests and answers like the service:

- service_call forwards a request to an internal service
- service_call needs a base URL
- Listing subscriptions on the billing service
- Reading a customer and a subscription
- Reporting usage to the billing service
- An error of the billing service is returned to the agent
- Sending an email through the mailler service
- Starting a campaign through the mailler service
- Reading the analytics overview
- Listing users on the auth service
- A tool without a configured service explains it (outline over four tools)
- The base URL falls back to the global setting
- A Unix socket URL gets a dedicated client that must be closed
