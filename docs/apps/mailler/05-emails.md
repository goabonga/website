# Listing and reading emails

Read access to the emails stored by the [sending](04-send.md) feature: a
paginated, filterable list and a detail view.

Emails are scoped to the calling client (see
[client identity](02-authentication.md)): a client lists and reads only the
emails it sent. Administrators see every client.

## Endpoints

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/api/v1/emails` | GET | `mailler:read` | Paginated list, newest first |
| `/api/v1/emails/{email_id}` | GET | `mailler:read` | Full details of one email |

### List

Query parameters:

| Parameter | Default | Description |
| --- | --- | --- |
| `page` | `1` | Page number, 1 or more |
| `page_size` | `20` | Items per page, 1 to 100 |
| `provider` | none | Keep only emails of this provider |
| `status` | none | Keep only emails with this status |
| `client_id` | none | Administrators only: keep only the emails of this client. Any other caller asking for a client other than its own gets `403` |

The response contains `items` (id, recipient, subject, provider, status,
`created_at`, `scheduled_at`, `sent_at`), `total`, `page`, `page_size` and
`pages` (1 when there is no email). Invalid parameters give `422`.

### Detail

`GET /api/v1/emails/{email_id}` returns the identifier, recipient, sender,
subject, HTML and text content, provider, provider message id, status,
error message, retry count, every lifecycle timestamp, the stored metadata
and the task id. An unknown identifier gives `404`, and so does the
identifier of an email owned by another client (its existence is not
revealed); a malformed one gives `422`.

## How it is tested

- pytest: `tests/test_routes_emails.py` and `tests/test_auth_integration.py`
  (authentication exercised through the real routes: missing token, scopes,
  revoked token, opaque token, token exchange), plus routing cases in
  `tests/test_main.py`.
- behave: `features/emails.feature` seeds emails in the in-process SQLite
  database and covers pagination, both filters, validation, detail,
  a send then read round trip, `404`, authentication and scope, and the
  isolation between clients (own emails only, foreign detail `404`, foreign
  filter `403`, administrator view).
