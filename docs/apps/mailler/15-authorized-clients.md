# Authorized clients

Mailler serves several applications (the clients). The registry lists the
applications that may use it and fixes, for each one, the identity its emails
are sent with. A caller can neither use the service without being registered
nor choose an arbitrary sender: the sender, the reply-to address and the
provider are forced or validated from the record of its client.

## The record

A record is identified by `client_id`, the OAuth2 client the tokens of the
application are issued to (the `client_id` claim, or `azp`, see
[client identity](02-authentication.md)).

| Field | Meaning |
| --- | --- |
| `client_id` | Unique identifier, matches the tokens of the application |
| `name` | Display name |
| `is_active` | An inactive client is refused (default `true`) |
| `from_email`, `from_name` | Default sender identity |
| `allowed_senders` | Other identities the client may choose, as `{"email", "name"}` objects |
| `reply_to` | When set, emails of the client can only use this reply-to address |
| `allowed_providers` | Providers the client may use |
| `default_provider` | Provider used when the request names none (always allowed) |
| `rate_limit_per_minute`, `daily_quota` | Optional [sending limits](16-client-limits.md) |
| `callback_url`, `callback_secret` | Optional [status callback](20-status-callbacks.md); the secret is never returned |

Provider names must be adapters of the service (`brevo`, `sendgrid`, `ses`,
`protonmail`, see [providers](03-providers.md)); the registry rejects any other
name.

## The gate

Every call of a regular client is checked against the registry, whatever the
route:

- no record gives `403` ("Client is not registered");
- an inactive record gives `403` ("Client is deactivated");
- an active client is remembered for `CLIENT_CACHE_TTL` seconds, so a
  deactivation reaches every API process within that time (`0` checks the
  registry on every call). Refusals are never remembered.

Administrators (see `ADMIN_SCOPE`) do not need a record. Work already accepted
is stopped too: the worker does not send the emails of a client deactivated in
the meantime (they become `failed` with the error "Client is deactivated") and
does not run its campaigns.

## Sender and provider rules

For `POST /send`, `POST /schedule` and the campaigns of a regular client:

| Request | Result |
| --- | --- |
| no `from_email` | The default identity of the record; `422` if the record has none |
| `from_email` that is the default or one of `allowed_senders` (case-insensitive) | That identity, with its own name |
| any other `from_email` | `403` "Sender address is not allowed" |
| `from_name` that differs from the name of the chosen identity | `403` "Sender name is not allowed" |
| `reply_to` while the record fixes one, and it differs | `403`; without a fixed reply-to the request value is kept |
| no `provider` | `default_provider` of the record; `422` if it has none |
| `provider` outside `default_provider` and `allowed_providers` | `403` "Provider is not allowed" |

A request without a provider is valid: `provider` is optional. The platform
settings `DEFAULT_FROM`, `DEFAULT_FROM_NAME` and `DEFAULT_PROVIDER` (all empty
by default) are never applied to a regular client; they only serve
administrators who have no record. Campaigns check their overrides when they
are created or updated; the worker then fills the missing values from the
record of the campaign's client.

## Administration API

All routes need the administration scope.

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/clients` | GET | Paginated list (`page`, `page_size`, `is_active`, `search` on id and name) |
| `/api/v1/clients` | POST | Register a client (`201`, `409` if already registered) |
| `/api/v1/clients/{client_id}` | GET | Read a record (`404` if unknown) |
| `/api/v1/clients/{client_id}` | PUT | Partial update; `is_active: false` deactivates the client |

Invalid addresses and unknown providers give `422`. There is no deletion:
deactivate a client instead, its data stays.

## Data model and migration

Alembic revision `006` creates `authorized_clients` (unique indexed
`client_id`, the fields above, JSON lists for the senders and providers,
timestamps). It also upgrades a database created before the data belonged to
clients: templates, contacts, contact groups and campaigns get their required
`client_id`, slug and email uniqueness becomes per client, and the rows (and
the unowned emails) that already exist are attributed to the client named by
`LEGACY_CLIENT_ID`. The migration stops with an explanation when such rows
exist and `LEGACY_CLIENT_ID` is empty. A database created by revisions `002`
to `005` of this version already has all of it and is left as it is. Register
the legacy client with the API before it is used again.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CLIENT_CACHE_TTL` | `30` | Seconds an active client stays accepted without a registry check; `0` disables the cache |
| `LEGACY_CLIENT_ID` | empty | Client that owns the data created before clients existed (read by migration `006` only) |

## How it is tested

- pytest: `tests/test_services_clients.py` (gate, cache, sender, reply-to and
  provider rules), `tests/test_routes_clients.py`,
  `tests/test_models_client.py`, `tests/test_migration_authorized_clients.py`
  (the `006` upgrade path on SQLite against legacy and already scoped
  schemas), the gate cases of `tests/test_auth_dependencies.py`, the
  registry cases of the send, schedule and campaign route tests and of
  `tests/test_tasks_send.py`.
- behave: `features/clients.feature` (administration, unregistered and
  deactivated clients, identities and providers, reply-to, missing sender or
  provider, scheduled emails, campaigns, administrators, and the workers
  stopping the work of a deactivated client). The authentication steps
  register the client of a token with a default record, unless a scenario
  asks for an unregistered one. The migration was not run on PostgreSQL.
