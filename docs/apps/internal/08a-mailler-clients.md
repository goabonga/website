# Mailler clients

The mailler service serves several applications. Its client registry lists those allowed to use
it and fixes, for each one, the identity its emails are sent with (see the
[authorized clients](../mailler/15-authorized-clients.md) and
[sending limits](../mailler/16-client-limits.md) of the service). This feature gives operators
holding `mailler:admin` the screens to manage that registry, instead of the
[`mailler clients` command](../mailler/17-command-line.md) or direct API calls. The steps to
connect a new application are in [onboarding an application](../mailler/22-multi-client-onboarding.md).

## What it adds

| Module | Role |
| --- | --- |
| `internal/services/mailler_client.py` | `list_clients`, `get_client`, `create_client` and `update_client`, which call `/api/v1/clients`. |
| `internal/routes/mailler.py` | The routes below, and the parsers of the sender and limit fields. |
| `internal/templates/admin/mailler/clients.html`, `client_form.html` | The list and the form that registers or edits a client. |

The pages belong to the Mailler section of the navigation (its link and the other links are
unchanged). The mailler dashboard shows a "Clients" button to users who hold `mailler:admin`.

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /mailler/clients | `mailler:admin` | List the clients (`page`, `search`, `status=active\|inactive`). |
| GET | /mailler/clients/new | `mailler:admin` | Registration form. |
| POST | /mailler/clients/new | `mailler:admin` | Register a client. |
| GET | /mailler/clients/{client_id}/edit | `mailler:admin` | Edit form. |
| POST | /mailler/clients/{client_id}/edit | `mailler:admin` | Update a client. |
| POST | /mailler/clients/{client_id}/deactivate | `mailler:admin` | Deactivate a client. |
| POST | /mailler/clients/{client_id}/activate | `mailler:admin` | Activate a client again. |

The `mailler:admin` scope is asked for in the token exchange of these pages (it is not one of
the `read`, `write` and `delete` scopes of the resource), as is the case for the navigation scopes.
Every action redirects with a `success` or `error` banner; an error carries the explanation of
the mailler service (already registered, invalid address, unknown provider, a callback URL
without secret...), whose validation messages are listed field by field.

## The record

| Field of the form | Meaning |
| --- | --- |
| OAuth client ID | Unique, no spaces, fixed once registered. The `client_id` (or `azp`) claim of the application's tokens; each OAuth client of an application is a client of its own. |
| Name | Display name. |
| Active | An inactive client is refused by the service; its queued emails and campaigns are stopped. |
| Default sender address and name | The identity used when a request names none. |
| Reply-to address | When set, emails of the client cannot use another one. |
| Other sender identities | One per line, `address` or `address, name`. |
| Allowed providers | Checkboxes for the providers configured on the service (`GET /api/v1/providers`); a provider the record has but the service does not configure is kept and flagged. |
| Default provider | Used when a request names none; always allowed. |
| Emails per minute, per day | Optional rate limit and daily quota, positive whole numbers; empty is unlimited. |
| Callback URL and secret | Optional signed status notifications. The secret has at least 16 characters, is write-only and never shown again. |

Registering sends the fields that are filled. **Editing applies every field of the form**: an
empty field removes the value (a limit becomes unlimited, a sender is cleared). The one exception
is the callback secret: leaving it empty keeps the current secret, unless the callback URL is
emptied too, which removes both. Deactivating and activating only change the `is_active` flag.
There is no deletion, as in the service: deactivate a client instead, its data stays.

The service stays the authority: it validates addresses, providers (it only knows its adapters)
and the callback URL (`https`, or `http` when it is configured to accept it); this application
only checks what it needs to build the request (an identifier without spaces, positive whole
numbers, well-formed sender lines).

## Mailler client

The four calls need the administration scope of the service and nothing else, so they request
`MAILLER_ADMIN_SCOPE` alone (an empty setting makes them unusable: the registry then answers
`403`). `create_client` and `update_client` raise `MaillerAPIError` with the service's message and
status code, like `send_campaign`; `list_clients` and `get_client` log a failure and return an
empty page or `None`.

## Settings

| Variable | Default | Notes |
| --- | --- | --- |
| `MAILLER_CLIENTS_PAGE_SIZE` | `20` | Rows per page of the client list |

`MAILLER_ADMIN_SCOPE` must be the service's `ADMIN_SCOPE`, see [mailler statistics](08-mailler.md#mailler-client).

## Tests

pytest:

- `tests/services/test_mailler_client.py`
- `tests/routes/test_mailler.py`
- `tests/routes/test_mailler_sidebar.py`

They cover the four client calls (path, administration scope alone, filters, escaping, error
messages of the service), the sender and limit parsers, the payload built for a registration and
for an update, every route handler (success, refusal by the service, no answer, invalid input,
authentication), the templates rendered for real and the pages through the application with the
token exchange of production (an administrator manages the clients; a user holding only `read`,
`write` and `delete` gets `403` and the service is never called).
`tests/routes/test_mailler_sidebar.py` also opens the three pages for every scope combination: the
links shown are the ones the scopes permit, a single one (Mailler) is active.

Behave scenarios (`features/mailler_clients.feature`):

- List the clients
- List the clients with a search and a status filter
- An unknown status filter is refused
- List without any client
- An inactive client can be activated again
- The list needs authentication
- The list needs the mailler admin scope
- The dashboard links to the clients for administrators only
- The dashboard hides the clients from other users
- View the registration form
- Register a client with its sender, providers, limits and callback
- The service can refuse a registration
- A client id with spaces is not registered
- A limit that is not a positive whole number is not registered
- Registering needs the mailler admin scope
- View the edit form of a client
- Edit the form of an unknown client
- Emptying the limits of a client removes them
- Emptying the callback URL removes the callback and its secret
- The service can refuse an update
- An invalid limit is not sent when editing
- Deactivate a client
- Activate a client again
- Deactivating an unknown client reports the service's answer
- Deactivating needs the mailler admin scope
- Sidebar on the clients list
- Sidebar on the registration form
- Sidebar on the edit form of a client
- Sidebar gated links follow the scopes on the clients list

The mailler client is replaced by an `AsyncMock`: the registry API was not called for real, so the
exact validation messages and the effect of a deactivation on a running service are not verified
here.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/mailler_clients.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The clients are listed with their sender and limits
- The dashboard links to the clients for administrators
- The dashboard hides the clients from other users
- The list needs the mailler admin scope
- An anonymous visitor comes back to the list after the login
- The list says when there is no client
- The clients are searched and filtered by status
- A client is registered with its sender, providers, limits and callback
- The service can refuse a registration and its answer is shown on the form
- A client id with spaces is stopped by the form
- A limit that is not a positive whole number is stopped by the form
- The edit form shows the record of the client
- The form of an unknown client sends the user back to the list
- Emptying the limits of a client removes them
- Emptying the callback URL removes the callback and its secret
- The service can refuse an update and its answer is shown on the form
- A client is deactivated after a confirmation
- Dismissing the confirmation keeps the client active
- An inactive client is activated again
- The answer of the service is shown when a client cannot be deactivated

The answers of the mailler service are shown on the form that submitted them, the link of the dashboard only appears for the `mailler:admin` scope, and the deactivation asks for a confirmation.
