# Customers

A customer is an end user (or organization) of a tenant. It is identified
inside its SaaS application by an `external_id` chosen by the tenant, and
mirrored as a Stripe customer whose metadata carries `saas_id` and
`external_id`.

## Endpoints

All routes live under `/platform/{saas_id}/customers`. An unknown `saas_id`
gives `404 SaaS app not found`; a customer of another tenant gives
`404 Customer not found`.

| Path | Method | Scope | Purpose |
|------|--------|-------|---------|
| `/platform/{saas_id}/customers` | POST | `billing:platform:write` | Create a customer (`201`) |
| `/platform/{saas_id}/customers` | GET | `billing:platform:read` | List customers, newest first |
| `/platform/{saas_id}/customers/{customer_id}` | GET | `billing:platform:read` | Read one customer |
| `/platform/{saas_id}/customers/{customer_id}` | PATCH | `billing:platform:write` | Update email, name or extra data |
| `/platform/{saas_id}/customers/{customer_id}/portal` | GET | `billing:platform:read` | Stripe billing portal URL |

### Request and response

```json
{
  "external_id": "user-42",
  "email": "user@example.test",
  "name": "Ada",
  "extra_data": {"plan_hint": "pro"}
}
```

- `external_id` is required and unique per tenant; a duplicate gives `409`.
- `email` is validated as an email address (this is where the
  `email-validator` dependency is needed).
- `extra_data` is stored locally and sent to Stripe as customer metadata.
- The list accepts `limit` (1 to `LIST_MAX_LIMIT`, default `LIST_DEFAULT_LIMIT`) and `offset`.
- The portal endpoint requires a `return_url` query parameter and answers
  `{"url": "..."}`, the Stripe Customer Portal session URL. The `return_url`
  must be covered by the `checkout_url_allowlist` of the tenant (see the
  SaaS applications page), otherwise the answer is `422`.
- The Stripe customer is created before the local record, and updated
  before the local record on `PATCH`.

Customers carry a `deleted_at` column (soft delete). It is set by the
Stripe webhook handler of a later feature and is not exposed by this API.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `LIST_DEFAULT_LIMIT` | `100` | Page size of the list endpoints when `limit` is not given |
| `LIST_MAX_LIMIT` | `1000` | Largest `limit` a caller can ask for |

`REDIRECT_ALLOWLIST_REQUIRED` (see the SaaS applications page) also decides
whether a portal `return_url` is accepted when the tenant lists no prefix.

## How it is tested

pytest (`apps/billing/tests/test_routes_platform_customers.py`):
`TestCreateCustomer`, `TestListCustomers`, `TestGetCustomer`,
`TestUpdateCustomer` and `TestGetCustomerPortal`, with a mocked database
session and Stripe service.

behave (`apps/billing/features/customers.feature`):

- Create a customer;
- Create a customer with duplicate external_id returns 409;
- List customers;
- Get a customer by ID;
- Update a customer;
- Get non-existent customer returns 404;
- Get customer portal URL;
- The customer portal refuses a return URL outside the allow-list.
