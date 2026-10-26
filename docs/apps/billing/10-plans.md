# Plans

The plans endpoint exposes the catalog of a SaaS application to its public
pricing page. It needs no authentication and is shaped for display: a plan
is a product, enriched with the features and limits stored in its
`extra_data`.

## Endpoint

| Path | Method | Scope | Purpose |
|------|--------|-------|---------|
| `/plans/{app_slug}` | GET | none | Active plans of an active SaaS application, identified by its slug |

An unknown or inactive slug gives `404 App '<slug>' not found`.

### Response

```json
{
  "app_slug": "example-app",
  "plans": [
    {
      "id": "...",
      "slug": "starter",
      "name": "Starter",
      "description": "...",
      "features": [{"label": "SSO", "highlight": false, "disabled": false}],
      "limits": {"max_seats": 10, "emails_per_day": -1},
      "prices": [
        {"id": "...", "currency": "usd", "unit_amount": 2900,
         "billing_type": "recurring", "interval": "month", "interval_count": 1}
      ],
      "is_recommended": true,
      "sort_order": 1,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

How the fields are built from a product:

- Only active products and active prices are returned.
- `features` come from `extra_data["features"]`; an entry can be an object
  (`label`, `highlight`, `disabled`) or a plain string label.
- `limits` come from `extra_data["limits"]`: a mapping of limit names to
  integers, `dict[str, int]` end to end. The names are chosen by the SaaS
  application (`max_seats`, `emails_per_day`, ...): the platform has no list
  of keys and does not interpret the values (what `-1` means, for instance,
  is a convention between the tenant and its own code). Entries whose value
  is not an integer (`null`, text, booleans, decimals) are left out, so an
  absent or `null` limit means the plan declares none. `limits` is `null`
  when the product has no `limits` document.
- `slug` is the `slug` column of the product, the plan identifier unique
  inside the tenant (`free`, `pro`, ...).
- `is_recommended` and `sort_order` come from `extra_data` (defaults
  `false` and `0`).
- Prices are sorted by amount (free or custom first), plans by
  `sort_order`.

The `extra_data` of a product is set through the `metadata` field of the
products endpoint, together with its `slug` field. Nothing is seeded: the
plans of a tenant are created through the API or the admin interface.

## Configuration

No new variable.

## How it is tested

pytest (`apps/billing/tests/test_routes_plans.py`): `TestListPlans`
(unknown slug, features as objects or strings, limits, price filtering and
ordering, sort order) and `TestPlanLimits` (arbitrary limit names, parsing
of non-integer entries) with a mocked database session.

behave (`apps/billing/features/plans.feature`), without authentication:

- List plans for an existing SaaS app;
- List plans for a non-existent slug returns 404;
- Plans expose the limits defined by the SaaS app;
- Two SaaS apps expose different limit names for the same plan slug.
