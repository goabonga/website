# Products

A product is an item of a tenant's catalog (for example a plan). Each
product is mirrored in Stripe: the API creates and updates the Stripe
product first, then stores the local record with the real Stripe
identifier.

## Endpoints

All routes live under `/platform/{saas_id}/products`. An unknown `saas_id`
gives `404 SaaS app not found`.

| Path | Method | Scope | Purpose |
|------|--------|-------|---------|
| `/platform/{saas_id}/products` | POST | `billing:platform:write` | Create a product (`201`) |
| `/platform/{saas_id}/products` | GET | `billing:platform:read` | List products, newest first |
| `/platform/{saas_id}/products/{product_id}` | GET | `billing:platform:read` | Read one product |
| `/platform/{saas_id}/products/{product_id}` | PATCH | `billing:platform:write` | Update a product |

### Request and response

```json
{
  "name": "Pro",
  "slug": "pro",
  "description": "For teams",
  "metadata": {"features": [{"label": "SSO"}, {"label": "Audit log", "disabled": true}]}
}
```

- `name` is required (1 to 255 characters); `description` is limited to
  1000 characters.
- `slug` is the plan identifier, unique inside the tenant (`409` on a
  duplicate, checked before Stripe is called) and free to reuse in other
  tenants: every tenant can have its own `free` or `pro`. It must match
  `^[a-z0-9]+(-[a-z0-9]+)*$`. When it is omitted it is taken from
  `metadata.slug`, then built from the name (`Pro Plan` gives `pro-plan`);
  `422` if nothing can be derived. It can be changed with `PATCH`. The slug
  is mirrored into `extra_data.slug` so that clients reading it there keep
  working.
- `metadata` is stored in the `extra_data` column and returned as
  `extra_data`. It is also sent to Stripe as metadata together with
  `saas_id`; Stripe only stores strings, so nested values such as `limits`
  or `features` are sent as JSON strings (see the Stripe service page) and
  `saas_id` cannot be overridden. Its optional `features` list is rendered into the Stripe
  description: enabled features are listed under a "Features:" heading,
  features flagged `disabled` are left out.
- `PATCH` also accepts `is_active`. Only the fields that are sent change;
  the Stripe product is updated with the same values (`active` follows
  `is_active`) before the local record.
- The list hides inactive products unless `include_inactive=true`.
- A product of another tenant is never returned: lookups filter on both
  `product_id` and `saas_id` (`404 Product not found`).

## Configuration

No new variable.

## How it is tested

pytest (`apps/billing/tests/test_routes_platform_products.py`):
`TestCreateProduct`, `TestListProducts`, `TestGetProduct` and
`TestUpdateProduct`, with a mocked database session and Stripe service,
including slug derivation, slug conflicts and slug updates.

behave (`apps/billing/features/products.feature`):

- Create a product;
- List products (active only by default);
- Get a product by ID;
- Update a product;
- Get non-existent product returns 404;
- A product takes the slug of its metadata;
- A plan slug cannot be used twice in a SaaS app;
- Two SaaS apps can use the same plan slug.
