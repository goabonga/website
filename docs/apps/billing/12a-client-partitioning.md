# Client partitioning

Scopes say what a client may do, not on whose data. Without partitioning, a
client holding `billing:platform:write` could read and change the customers
and subscriptions of every SaaS application, so the service could only be
shared between applications that trust each other. Client partitioning adds
the missing question: **which SaaS applications may this OAuth client act
on?**

## Model

`saas_client_bindings` (revision `006`, empty after the migration) links an
OAuth client, identified by the `client_id` of its access tokens, to a SaaS
application. A client can be bound to several applications and an
application can have several clients; `(saas_app_id, client_id)` is unique
and a binding disappears with its application.

## Rules

Applied by `billing.partition.PartitionGuard` to every route that targets a
SaaS application:

| Caller | Result |
|--------|--------|
| Token with the admin scope | Allowed on every SaaS application |
| Client bound to the application | Allowed |
| Client bound to other applications only | `403 This client is not authorized for this SaaS app` |
| Client with no binding at all | `403`, unless `PARTITION_ALLOW_UNBOUND=true` |
| Token that does not identify its client | `403` |

The scopes still apply on top: being bound does not grant `billing:platform:write`.
The check runs before the route, so a refused request reads and writes
nothing, and an unknown application answers `403` like an unauthorized one:
a client cannot probe which identifiers exist.

The admin scope is `billing:admin` by default (`PARTITION_ADMIN_SCOPE`). It
must be carried by the token itself; a scope that the auth service would
only grant through token exchange does not count. A wildcard such as
`billing:*` includes it.

### Which client

The client is the one that obtained the token presented by the caller: its
`client_id` claim, or `azp` for user tokens. It is read from the
introspection of that token, never from the token exchange this service
performs to check scopes (that token belongs to the service's own client),
and never defaults to the service's own client id.

### Protected routes

| Routes | Protection |
|--------|------------|
| `/platform/{saas_id}/...` (products, prices, customers, subscriptions and their actions) | Guard on `{saas_id}` |
| `/platform/saas/{saas_id}`, `PATCH` and `.../sync-stripe` | Guard on `{saas_id}` |
| `/usage/{saas_id}/...` | Guard on `{saas_id}` |
| `POST /checkout/session` | Guard on the `saas_id` of the body, before anything is read |
| `GET /plans/{app_slug}` | A token with `billing:platform:read` and a binding to the application; an application the client may not see is `404`, like an unknown slug. With `PLANS_PUBLIC=true` the endpoint is served without a token (public pricing page) |
| `GET /platform/saas` | Lists only the applications the caller may act on, all of them for the admin scope |
| `POST /platform/saas` | Admin scope: a new application is bound to nobody yet |
| `/platform/saas/{saas_id}/clients...`, `/platform/clients/{client_id}/saas` | Admin scope |
| `/health` and the routes that are not about one application | Not concerned |

## Managing the bindings

Admin API (scope `billing:admin`):

| Path | Method | Purpose |
|------|--------|---------|
| `/platform/saas/{saas_id}/clients` | GET | List the clients bound to an application |
| `/platform/saas/{saas_id}/clients/{client_id}` | PUT | Bind a client (`201`, or `200` if it already was) |
| `/platform/saas/{saas_id}/clients/{client_id}` | DELETE | Unbind a client (`204`, `404` if it was not bound) |
| `/platform/clients/{client_id}/saas` | GET | List the applications a client is bound to |

Command line, which talks to the database (`DATABASE_URL`) and therefore
works before any client can reach the API:

```bash
uv run --package billing billing-admin saas create --name "Example App" --slug example-app \
    --checkout-url https://app.example.test
uv run --package billing billing-admin saas list
uv run --package billing billing-admin client bind --saas example-app --client-id <oauth client id>
uv run --package billing billing-admin client unbind --saas example-app --client-id <oauth client id>
uv run --package billing billing-admin client list [--saas example-app] [--client-id <oauth client id>]
```

`--saas` takes the slug or the identifier. Every command prints JSON; it
exits with 1 and a message on stderr when the application is unknown, the
slug is taken or the binding does not exist.

## Onboarding a new SaaS application

Nothing about a tenant is seeded or written in code: a new application is
created, bound and filled through the API or the command line.

1. **Create the OAuth client** of the application in the auth service, with
   the scopes it needs (`billing:platform:read`, `billing:platform:write`,
   `billing:checkout:write`, `billing:usage:write` as appropriate). Never
   give it `billing:admin`.
2. **Create the application** with the admin scope or the command:
   `billing-admin saas create ... --checkout-url <origin of its pages>`. Set
   `webhook_url` and `webhook_secret` (API or admin interface) to receive
   subscription events.
3. **Bind the client**: `billing-admin client bind --saas <slug> --client-id <id>`.
4. **Create the catalog** with the bound client (or an admin): products with
   their `slug` (`free`, `pro`, ... may be reused by every application) and
   `metadata` (`features`, `limits` with the application's own names), then
   prices. Products and prices are created in Stripe at the same time, so
   `STRIPE_SECRET_KEY` must be configured.
5. **Wire the application**: it reads `/plans/<slug>`, creates checkout
   sessions with its `saas_id`, receives the webhooks and maps them by the
   `plan.slug`, never by a hard-coded identifier shared with the billing
   service.

Operators who administer every application use a client holding
`billing:admin`; applications never do.

## Moving an existing deployment

Before this feature every client could act on every application. After
migrating, clients have no binding and are refused. Either bind them
(`billing-admin client bind ...`, recommended), or set
`PARTITION_ALLOW_UNBOUND=true` temporarily: a client without any binding
is then treated as before, while a client with at least one binding is held
to its bindings. The plans also need a token now, unless `PLANS_PUBLIC=true`.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `PARTITION_ADMIN_SCOPE` | `billing:admin` | Scope that crosses applications and manages the bindings |
| `PARTITION_ALLOW_UNBOUND` | `false` | Let a client without any binding act on every application (legacy mode) |
| `PLANS_PUBLIC` | `false` | Serve `/plans/{app_slug}` without a token |

The command also reads `DATABASE_URL`. The entry point `billing-admin` is
declared in `apps/billing/pyproject.toml`.

## How it is tested

pytest (`apps/billing/tests`):

- `test_partition.py`: the guard on its own (bound, other, several,
  unbound, legacy mode, admin and wildcard, configurable admin scope, no
  client id, route-reduced scopes) and cross-application isolation through
  real HTTP requests with two applications: the platform routes (16
  routes refused with one query only and nothing written), usage, checkout,
  plans, listing and creation of applications;
- `test_routes_platform_clients.py`: list, bind (created and idempotent),
  unbind, reverse lookup, and the admin-only rule;
- `test_cli.py`: the command against an in-memory SQLite database;
- `test_auth_dependencies.py` and `test_auth_models.py`: the client is the
  presented token's, with `azp` and without any fallback;
- `test_migrations.py`: revision `006`.

The route tests of the other features use a permissive guard fixture
(`AllowAllGuard` in `conftest.py`) so that their mocked sessions are not
asked for bindings.

behave (`apps/billing/features/partitioning.feature`), with two real
applications on the in-memory database and tokens of distinct OAuth
clients:

- A bound client reads the data of its own SaaS app;
- A bound client cannot read the products of another SaaS app;
- A bound client cannot read a customer of another SaaS app;
- A bound client cannot cancel a subscription of another SaaS app;
- A refused write leaves the other SaaS app untouched;
- A bound client cannot read or change the record of another SaaS app;
- A bound client reports usage on its own SaaS app only;
- A bound client creates checkout sessions for its own SaaS app only;
- A checkout cannot mix a customer of one SaaS app with a price of another;
- Plans are served for the bound SaaS app only;
- Two SaaS apps expose their own limits under the same plan slug;
- A client without binding is denied;
- A client without binding sees no SaaS app;
- A bound client lists only its own SaaS app;
- The admin scope crosses SaaS apps;
- Only the admin scope can create a SaaS app;
- A bound client cannot bind itself to another SaaS app;
- The admin binds a client, then unbinds it;
- The admin lists the bindings of a SaaS app and of a client;
- A token without OAuth client is denied.
