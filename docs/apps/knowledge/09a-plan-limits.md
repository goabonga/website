# Plan limits from billing

The [usage quotas](07-quotas.md) compare what an account uses with the limits of its plan.
Those limits are not in the code: they are the `limits` of the plans in the billing service,
the one place where the plans are edited, so changing a plan in billing changes what
customers may do without a deployment. When billing cannot tell, a **fail-safe** that the
operator configures applies instead.

## Where the limits come from

`knowledge.services.plan_limits.get_plan_limits(plan_slug)` is what
`QuotaService.get_plan_limits` and `get_limit` call (they are asynchronous). The slug is the
value of the account's `PlanType` (`free`, `starter`, `pro`, `enterprise`); the enum only names
the plans, it carries no limit. The resolution is:

1. Billing: `BillingClient.get_plan_by_slug(slug)` reads `GET /plans/<BILLING_APP_SLUG>`
   (token-authenticated, see the [billing integration](09-billing.md)) and the plan's `limits`
   is returned as it is, a `dict[str, int]`. The names are chosen in billing for this
   application (`max_collections`, `max_documents_per_collection`, `max_total_documents`,
   `max_api_calls_per_month`, `max_storage_bytes`, ...), nothing in the code lists them; `-1` is
   unlimited and a limit the plan does not define is `0`. The plan list is cached in Redis by
   the billing client (`BILLING_CACHE_TTL`).
2. The fail-safe, when billing cannot answer: billing is not configured (no URL or socket, or no
   `BILLING_APP_SLUG`), it is unreachable or refuses the request, the plan is not in the list,
   or the plan declares no `limits` at all. A plan that declares an empty `limits` object is
   an answer: it allows nothing.

The fail-safe is the `QUOTA_FALLBACK_LIMITS` setting, a JSON object of plan slug to limits,
where `"*"` is used for the plans that are not listed:

```bash
export QUOTA_FALLBACK_LIMITS='{"free": {"max_collections": 3, "max_total_documents": 200},
  "*": {"max_collections": 1}}'
```

It is empty by default, which means that nothing is allowed while billing is unavailable and
unconfigured: choose the values you accept to grant during an outage.

After a failure billing is not asked again for `BILLING_FAILURE_BACKOFF` seconds, and the
fail-safe applies in the meantime, so that an outage does not add the timeout of a request to
every quota check. A warning is logged each time billing cannot answer.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `QUOTA_FALLBACK_LIMITS` | `{}` | Fail-safe limits `{plan slug: {limit name: integer}}`, `"*"` for the other plans. |
| `BILLING_FAILURE_BACKOFF` | `30` | Seconds during which the fail-safe applies after billing failed, before it is asked again. |

The billing settings (`BILLING_API_URL`, `BILLING_APP_SLUG`, `BILLING_CACHE_TTL`, ...) are on the
[billing integration](09-billing.md) page.

## Tests

pytest:

- `unit/test_plan_limits.py`: billing limits win, any limit name and `-1`, the fail-safe when
  billing is down, not configured, without the plan or without limits, the wildcard, the
  back-off and its end, an empty `limits` object, and the quota service using both sources.

behave (`features/plan_limits.feature`), with the real billing client on a mocked transport:

- The limits of the plan are the ones of billing
- Limits are named by the application and can be unlimited
- A limit billing does not define is zero
- Creating a collection is refused with the limit of billing
- Billing being down, the fail-safe limits apply
- A plan the fail-safe does not list uses the wildcard entry
- An outage does not make every check wait for billing
- Billing is asked again after the outage
- Billing without the plan applies the fail-safe
- Without billing configuration the fail-safe applies

Not verified: a real billing service; the plans were served by a mocked transport.
