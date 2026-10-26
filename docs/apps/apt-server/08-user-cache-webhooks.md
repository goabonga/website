# User cache and webhooks

Packages are owned by, and shared with, OIDC subjects: opaque identifiers that
are unreadable in a UI. This feature keeps a local copy of user profiles and
keeps it current from signed events sent by the `auth` service, without
calling `auth` on every page load.

## Data model

Migration `002` (`alembic/versions/002_add_user_cache.py`) adds `user_cache`:

| Column | Description |
| --- | --- |
| `sub` | OIDC subject, primary key |
| `email` | Email, indexed |
| `name` | Display name (default empty) |
| `avatar_url` | Avatar URL (default empty) |
| `updated_at` | Last update (UTC) |

`UserCache.display` is the email, else the name, else the `sub`.

## Service

`apt_server.services.user_cache`:

- `upsert(db, sub=, email=, name=, avatar_url=)` inserts or updates a profile;
  blank values never erase existing ones.
- `resolve_display(db, identifier)` returns the display of a `sub` or an email,
  or the identifier itself when unknown.
- `resolve_many(db, identifiers)` resolves a list in one query.

The web login (see the web sessions page) also fills the cache.

## Webhook endpoint

`POST /webhooks/auth` (hidden from OpenAPI) receives events from `auth`. The
headers `X-Webhook-Signature` and `X-Webhook-Event` are required (422 when
absent).

The signature has the form `t=<unix timestamp>,v1=<hex>` where the digest is
the HMAC-SHA256 of `<timestamp>.<raw body>` with `WEBHOOK_SECRET`. A bad
digest, a malformed header or a timestamp older than five minutes answers 401.
When `WEBHOOK_SECRET` is empty the check is skipped and a warning is logged,
which is only meant for development.

| Event | Effect |
| --- | --- |
| `user.created`, `user.updated`, `user.email_changed`, `user.email_verified` | Upsert the profile (`user_id` or `id`, `email` or `new_email`, `name` or `display_name`, `picture` or `avatar_url`); events without both identifier and email are ignored |
| email change (`old_email` or `previous_email` present) | Also rewrite ACL grants addressed to the old email |
| `user.deleted` | Remove the profile |
| anything else | Acknowledged and ignored |

The answer is always `{"status": "ok"}` for an accepted delivery.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `WEBHOOK_SECRET` | empty | HMAC secret of the webhook subscription; also read from systemd credentials |

## Tests

- pytest: `tests/test_user_cache.py` (upsert, blank values, resolution) and
  `tests/test_webhooks.py` (signature verification, every event, field
  aliases, ACL rewrite, deletion, rejected deliveries); `tests/test_models.py`
  and `tests/test_migrations.py` also cover the new table and revision `002`.
- behave: `features/user_cache_webhooks.feature` with the scenarios "A created
  user is cached", "An updated email replaces the cached one", "Access grants
  follow an email change", "A deleted user is removed from the cache", "An
  event with a bad signature is refused" and "Cached profiles resolve
  identifiers to display names".
