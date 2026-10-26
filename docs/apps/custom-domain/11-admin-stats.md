# Administration statistics

Four read-only endpoints under `/api/v1/admin/stats` give administrators the
numbers needed to run the service: how many domains are in which state, how
many are about to lose their certificate, which clients own the most domains
and what changed recently.

Every endpoint requires **both** the administration scope (`ADMIN_SCOPE`,
`custom-domain:admin` by default) and its `:stats` variant, for example
`custom-domain:admin:stats`.

## Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/admin/stats/overview` | GET | Domain, client and template counters. |
| `/api/v1/admin/stats/top-clients` | GET | Clients ranked by number of live domains. Query: `limit` (default 10). |
| `/api/v1/admin/stats/recent-activity` | GET | Most recently updated live domains. Query: `limit` (default 20). |
| `/api/v1/admin/stats/dashboard` | GET | The three views above in one answer: the overview, the top 5 clients and the 10 latest activities. |

### Overview

`{domains, clients, templates}`.

`domains`:

| Field | Meaning |
| --- | --- |
| `total` | Every row, soft-deleted ones included. |
| `deleted` | Rows with `deleted_at` set. |
| `by_status` | Count per status among the non-deleted rows (all eight statuses are present). |
| `active`, `failed` | Counts from `by_status`. |
| `pending` | `pending` + `dns_verifying` + `dns_verified` + `ssl_provisioning`. |
| `created_last_24h`, `created_last_7d`, `created_last_30d` | Rows created in the window (deleted ones included). |
| `activated_last_24h`, `activated_last_7d` | Active, non-deleted domains whose certificate was provisioned in the window. |
| `ssl_expiring_soon` | Active, non-deleted domains whose certificate expires within the next `CERTIFICATE_RENEWAL_DAYS` days (the window in which the maintenance task renews certificates). |
| `ssl_expired` | Active, non-deleted domains whose certificate expiry date has passed. |

`clients`: `total`, `active`, `inactive`. `templates`: `total`, `active`,
`domains_using_custom` (non-deleted domains with a template of their own) and
`domains_using_default` (the others).

### Top clients

A list of `{client_id, name, domain_count, active_count}` for the registered
clients that own at least one non-deleted domain, sorted by `domain_count`
descending.

### Recent activity

A list of `{domain, client_id, status, created_at, updated_at}` for non-deleted
domains, most recently updated first.

## Data model

Counts rows of `custom_domains`, `authorized_clients` and `nginx_templates`;
nothing is written and no migration is added. The overview issues one query
per counter.

## How it is tested

- pytest: `test_routes_admin_stats.py` (HTTP-level tests with a mocked
  session) and `test_routes_admin_stats_unit.py` (the route functions called
  directly with scripted counters).
- behave: `features/admin_stats.feature` runs the endpoints on an in-memory
  database with seeded domains, clients and templates: an empty overview,
  counters following the statuses, certificates expiring soon or already
  expired, client and template counts, the top clients ranking, recent activity,
  the dashboard and the missing-scope case.
