# Usage quotas and API call tracking

Plans bound how much each account can store, and every successful API call is
counted per tenant and month. This feature adds the quota service and the
tracking middleware; the web UI later displays the same figures.

## Plan limits

The code contains no limit: a limit is a named integer (`max_collections`,
`max_documents_per_collection`, `max_total_documents`, `max_api_calls_per_month`,
`max_storage_bytes`), and the values of each plan are configuration.
`knowledge.services.plan_limits` resolves them for the slug of a `PlanType`
(`free`, `starter`, `pro`, `enterprise`; the enum only names the plans and carries
no limits):

- `-1` means unlimited;
- a limit the plan does not define is `0`, which allows nothing;
- the limits come from the `QUOTA_FALLBACK_LIMITS` setting, a JSON object of
  plan slug to limits. The entry of the plan wins, then the `"*"` entry, then
  nothing.

```bash
export QUOTA_FALLBACK_LIMITS='{"free": {"max_collections": 3, "max_total_documents": 200},
  "enterprise": {"max_collections": -1, "max_total_documents": -1}, "*": {}}'
```

Nothing is set by default, so a fresh installation allows nothing until the
deployment defines its plans. The billing integration later makes the billing
service the first source of the limits and keeps this setting as the fail-safe
when the service cannot be reached.

## QuotaService

`QuotaService(db)` works for both kinds of collection owners:

- `get_owner_plan(owner_type, owner_id)`: the plan of a personal account
  (`user_plans`, `free` when there is no row) or of an organization.
- `check_quota_for_owner(...)` returns a `QuotaStatus` (`current`, `limit`,
  `remaining`, `percentage_used`, `is_exceeded`, `is_near_limit` at 80 percent,
  `is_unlimited`) for `max_collections`, `max_total_documents` or
  `max_storage_bytes`.
- `enforce_quota_for_owner(...)` and `enforce_collection_quota_for_owner(...)`
  raise `QuotaExceededError(quota_type, current, limit)` when the limit is
  reached.
- `get_usage_for_owner(...)` returns a `UsageStats` snapshot.

Legacy tenant-based helpers (`check_quota`, `get_usage`, `enforce_*_quota`)
remain for organizations, plus the usage counters: `increment_usage` upserts a
`usage_records` row per tenant, metric and month (`YYYY-MM`), and
`record_api_call`, `record_document_added`, `record_search` and
`record_embedding` are thin wrappers. `format_bytes` renders sizes for the UI.

The public REST routes do not enforce these quotas yet; the service is
consumed by the web interface and by the tracking middleware described below.

## API call tracking

`APITrackingMiddleware` is added to the public application. For every request
under `/api/v1/` (or `/v1/`) that ends with a `2xx` status, it records one
`api_calls` usage for the tenant found in `request.state.tenant_id` (set by the
[authentication](02-authentication.md) dependency), using its own database
session. Health checks, other paths and failed calls are ignored, and a
failure to record is logged as a warning without affecting the response.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `RATE_LIMIT_REQUESTS` | `100` | Declared in the settings, not read by the code yet. |
| `RATE_LIMIT_WINDOW` | `60` | Declared in the settings (seconds), not read by the code yet. |
| `QUOTA_FALLBACK_LIMITS` | `{}` | JSON object `{plan slug: {limit name: integer}}`, `"*"` for the other plans; `-1` is unlimited and a missing limit is `0`. |

## Tests

pytest:

- `unit/test_quota_service.py`: `QuotaStatus` arithmetic, plan limits read from
  the settings (plan entry, `*` entry, nothing configured, JSON from the
  environment), owner
  and tenant quota checks and enforcement, usage statistics, counters and
  `format_bytes`.
- `unit/test_middleware.py`: the tracking middleware records successful API
  calls only, skips health and non-API paths and survives recording errors.

behave (`features/quotas.feature`):

- Plan limits (outline over the free, starter, pro and enterprise plans, configured
  in the scenario background)
- A limit that is not configured is zero
- A quota with room left is not exceeded
- A quota close to its limit is flagged
- A quota at its limit is exceeded
- An unlimited quota is never exceeded
- Creating a collection is refused when the plan limit is reached
- Creating a collection is allowed below the plan limit
- Enterprise organizations have no collection limit
- A successful API call is recorded for the tenant
- A failed API call is not recorded
- Calls outside the API are not recorded
- A tracking failure never fails the request
