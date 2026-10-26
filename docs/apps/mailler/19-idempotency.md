# Idempotent sending

A client that is not sure a request reached the service (a timeout, a retry
after a crash) must be able to repeat it without sending the email twice.
`POST /api/v1/send` and `POST /api/v1/schedule` accept an `Idempotency-Key`
header for that.

## Behaviour

- The key is any string of 1 to 255 characters chosen by the client (an
  identifier of the business event, for example the id of an invitation). A
  longer or empty key gives `422`.
- The first request with a key creates the email as usual and stores the key
  with it. A later request with the same key from the same client creates
  nothing, queues nothing and returns `200` with the identifier and the status
  of the first email (`queued`, or `scheduled` for `/schedule`) and the
  message "Already submitted with this Idempotency-Key". The `task_id` is
  returned once the worker has taken the email.
- A repeated request is answered before anything else is checked: it is not
  counted again by the [sending limits](16-client-limits.md) and its content is
  not rendered or validated again.
- Keys are scoped to the client: two applications can use the same key.
- A key that was used for an email to another recipient is refused with `422`
  ("Idempotency-Key was already used for another request"). Only the recipient
  is compared, not the rest of the body.
- Two identical requests arriving at the same moment are handled too: the
  database refuses the second email, which is answered like a repeat.
- Without the header every request sends an email.

## Data model and migration

Alembic revision `008` adds the nullable `emails.idempotency_key` and the
unique constraint `uq_emails_client_idempotency` on `(client_id,
idempotency_key)`; emails without a key are not constrained. The steps check
whether they are needed, so the migration can be run again. Keys are kept as
long as the emails are (`EMAIL_RETENTION_DAYS`, see
[scheduling](07-schedule.md)).

## How it is tested

- pytest: `tests/test_services_idempotency.py`, the idempotency cases of the
  send and schedule route tests (stored key, repeat, recipient mismatch, race,
  length), `tests/test_models_email.py` and
  `tests/test_migration_email_idempotency.py` (the `008` upgrade and downgrade
  on SQLite).
- behave: `features/idempotency.feature` (repeat, no key, two clients, another
  recipient, scheduling, limits, maximum length) against the in-process SQLite
  database. The migration was not run on PostgreSQL.
