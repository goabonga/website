# Inbound email processing

Optional feature: mailler polls a mailbox over IMAP (the Protonmail Bridge),
stores the messages it finds and forwards each one to a target service as a
webhook in the Brevo "inbound parsing" format. It is disabled by default.

## Enabling it

Set `INBOUND_ENABLED=true`. This registers the inbound API routes when the
application starts and adds the polling tasks to the Celery beat schedule.
The mailbox credentials are the Protonmail ones used for sending
(`PROTONMAIL_HOST`, `PROTONMAIL_USER`, `PROTONMAIL_PASSWORD`) plus the IMAP
port below; `INBOUND_WEBHOOK_URL`, `INBOUND_IMAP_PORT` and
`INBOUND_ATTACHMENTS_DIR` must be set too: the poll task skips its run (and
says why) while one of them, or the host, is missing.

The mailbox is shared by the whole platform and not tied to a client, so
reading it requires the administration scope (`ADMIN_SCOPE`, see
[client identity](02-authentication.md)); a regular client gets `403`.

## Endpoints

Available only when inbound processing is enabled.

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/api/v1/inbound/emails` | GET | administration scope | Paginated list (`page`, `page_size`, `status`, `from_email`) |
| `/api/v1/inbound/emails/{id}` | GET | administration scope | Full message with its attachments |
| `/api/v1/inbound/attachments/{download_token}` | GET | none | Download an attachment; the unguessable token is the credential |

An unknown token or id gives `404`, an expired attachment `410`.

## Tasks

All tasks are in `mailler.tasks.inbound`.

| Task | Schedule | Description |
| --- | --- | --- |
| `poll_inbound_emails` | every `INBOUND_POLL_INTERVAL` seconds | Fetch unseen messages, parse and store them, deliver the webhook, then move delivered messages to the processed folder |
| `retry_failed_inbound` | every 5 minutes | Re-deliver messages whose delivery failed, up to 3 attempts (20 per run) |
| `cleanup_expired_attachments` | daily at 04:00 UTC | Delete expired attachment files and rows |

Details:

- The connection uses IMAP with STARTTLS and logs in with the Protonmail
  credentials. The processed folder (`INBOUND_PROCESSED_FOLDER`) is created
  when missing. A message whose delivery failed stays in the inbox.
- Parsing (`mailler.services.inbound.parser`) decodes headers, extracts the
  HTML and text bodies, addresses, selected headers and attachments.
- Messages are de-duplicated on their `Message-ID`: a message already
  forwarded is only moved. Attachments are written under
  `INBOUND_ATTACHMENTS_DIR/<message uuid>/` with a sanitised file name and
  get a download token valid for `INBOUND_ATTACHMENT_TTL` seconds.
- The webhook payload (`mailler.services.inbound.webhook`) follows the Brevo
  format (From, To, Cc, Subject, HTML and text bodies, extracted markdown,
  headers, attachments with their `DownloadToken`). It is posted with a
  30 second timeout; a 2xx answer counts as delivered. When
  `INBOUND_WEBHOOK_SECRET` is set the request carries an
  `X-Webhook-Signature` HMAC-SHA256 header.
- A message is `received` when stored, `forwarded` once delivered and
  `failed` otherwise (with the status code, the error message and a retry
  counter).

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `INBOUND_ENABLED` | `false` | Enable the routes and the polling tasks |
| `INBOUND_IMAP_PORT` | `0` | IMAP port of the mailbox (the host is `PROTONMAIL_HOST`); required |
| `INBOUND_POLL_INTERVAL` | `30` | Polling interval in seconds |
| `INBOUND_WEBHOOK_URL` | empty | Target URL for forwarded messages |
| `INBOUND_WEBHOOK_SECRET` | empty | Optional HMAC secret for the forwarded request (secret) |
| `INBOUND_PROCESSED_FOLDER` | `Processed` | IMAP folder for delivered messages |
| `INBOUND_ATTACHMENTS_DIR` | empty | Attachment storage directory; required |
| `INBOUND_ATTACHMENT_TTL` | `86400` | Attachment lifetime in seconds |

`INBOUND_WEBHOOK_SECRET` can be provided as a systemd credential like the
other secrets.

## Data model and migration

Alembic revision `005` creates `inbound_emails` (message id, sender,
recipients and copies as JSONB, subject, bodies, headers, status, webhook
response code, error message, retry counter, IMAP uid, timestamps) and
`inbound_attachments` (file name, content type and length, content id,
unique download token, file path, expiry), with cascading deletes.

## Dependencies

`html2text` converts the HTML body to markdown for the webhook payload.

## How it is tested

- pytest: `tests/test_routes_inbound.py`, `tests/test_services_inbound_imap.py`,
  `tests/test_services_inbound_parser.py`, `tests/test_services_inbound_webhook.py`,
  `tests/test_tasks_inbound.py`, conditional route and beat registration in
  `tests/test_main.py` and `tests/test_celery_config.py`, and the settings
  defaults in `tests/test_config.py`.
- behave: `features/inbound.feature` runs the polling, retry and cleanup
  tasks end to end with an in-memory mailbox (real RFC 822 messages built
  with the standard library) and a fake webhook target; parsing, storage,
  attachments and the API are real. It also covers listing, filters,
  detail, attachment download (valid, expired, removed), scopes and
  authentication, the poll task skipping while the mailbox is not
  configured, and the administration-only access to the stored messages.
