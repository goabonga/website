# SaaS client bindings

The billing service is shared by several SaaS applications. To keep them apart, it only lets an
OAuth client act on the SaaS apps it is **bound** to (see the
[client partitioning](../billing/12a-client-partitioning.md) of the billing service). This
feature gives operators holding `billing:admin` the screens to list, add and remove those
bindings from the page of a SaaS app, instead of the `billing-admin client` command.

## What it adds

| Module | Role |
| --- | --- |
| `internal/services/billing_client.py` | `list_saas_clients`, `bind_client` and `unbind_client`, which call the admin API of the billing service. |
| `internal/routes/billing.py` | The two form routes below, and the bindings passed to the SaaS app page. |
| `internal/templates/admin/billing/saas_detail.html` | The "OAuth clients" card. |

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| POST | /billing/saas/{saas_id}/clients | `billing:admin` | Bind the OAuth client given in the `client_id` field. |
| POST | /billing/saas/{saas_id}/clients/unbind | `billing:admin` | Remove the binding of the `client_id` field. |

Both redirect back to `/billing/saas/{saas_id}` with a `success` or `error` banner. The
`client_id` is stripped; an empty identifier or one containing spaces is refused before the
billing service is called (it accepts neither). Binding an already bound client is not an
error.

## Page

The page of a SaaS app (`/billing/saas/{saas_id}`) shows an **OAuth clients** card to users who
hold `billing:admin`: the clients bound to the app with the date of the binding, an "Unbind"
button per client and a field to bind another one. Other users do not see the card and the
bindings are not even fetched. The identifier is the `client_id` of the OAuth client (the
`client_id` claim of its tokens, or `azp` for tokens issued to a user); create the OAuth client
at the identity provider first.

An app with no bound client can only be reached by administrators (unless the billing service
runs in its legacy mode, `PARTITION_ALLOW_UNBOUND`). Removing the last binding of an application
therefore cuts it off at once.

## Billing client

The three calls use the admin scope alone (`BILLING_ADMIN_SCOPE`, see
[billing administration](06-billing.md#billing-client)); the billing service answers `403` to a
token that does not carry it. The client identifier is percent-encoded in the path. A failure
is logged and gives `None` (bind), `False` (unbind) or an empty list (list).

## Settings

No new variable: `BILLING_ADMIN_SCOPE` must be the scope the billing service names in
`PARTITION_ADMIN_SCOPE`, and the OAuth client of this application must hold it.

## Tests

pytest:

- `tests/services/test_billing_client.py`
- `tests/routes/test_billing.py`
- `tests/routes/test_billing_sidebar.py`

They cover the three client calls (path, admin access, escaping, failures), the two routes
(success, failure, invalid identifier, authentication), the page handler (bindings fetched for
an administrator only) and the card rendered with the real template. The billing sidebar tests
now render the SaaS app page with a binding, for every scope combination.

Behave scenarios (`features/billing_clients.feature`):

- The SaaS app page lists the bound OAuth clients
- The SaaS app page says when no OAuth client is bound
- The bound clients are hidden from users without the admin scope
- Bind an OAuth client to a SaaS app
- Binding an OAuth client can fail
- A client id with spaces is not bound
- Binding needs the billing admin scope
- Binding requires authentication
- Unbind an OAuth client from a SaaS app
- Unbinding an OAuth client can fail

The billing client is replaced by an `AsyncMock`: nothing was run against a real billing service.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/billing_clients.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The page of a SaaS app lists the bound OAuth clients
- The page says when no OAuth client is bound
- The bound clients are hidden from users without the admin scope
- An OAuth client is bound from the page of the SaaS app
- Binding an OAuth client can fail
- A client id with spaces is stopped by the form
- An OAuth client is unbound from the page of the SaaS app
- Unbinding an OAuth client can fail

The card is read with the real scopes: a user holding `billing:admin` sees the bound clients and the binding form (a client id with spaces is stopped by the form itself), a user without it neither sees nor fetches them.
