# Share notification emails

Sharing a package from the dashboard with a user identified by an email
address sends that user a message through the internal `mailler` service. The
feature is optional: with no email backend configured nothing is sent.

## Behaviour

- Triggered by `POST /dashboard/{id}/share` after the grant is stored, only
  when the grantee type is `user` and the value contains `@`. Groups and opaque
  identifiers never produce a message. A rejected duplicate grant does not
  notify again.
- The message runs as a FastAPI background task, after the response is sent.
  Failures are logged and never affect the share itself (including a mailler
  outage, a missing configuration or an authentication error).
- The subject is `<sharer> shared <package> <version> with you`. The body is
  the MJML template `templates/emails/package_shared.mjml`, compiled to HTML by
  `mrml` on first use and cached in memory. It lists the package, version,
  architecture, component and granted role, shows the install command and has
  a button to the package page. Placeholders use the `%name%` form and are
  rendered with Jinja2 after compilation. The values are inserted as given,
  without HTML escaping.
- The package link is `https://<request host>/packages/<id>`.

## Mailler client

`apt_server.services.mailler` authenticates with the OAuth2
`client_credentials` flow (scope `mailler:send`) against
`MAILLER_AUTH_URL`, or the issuer when empty, caches the access token until one
minute before it expires, then calls `POST /api/v1/send` on `MAILLER_URL` with
the recipient, subject, HTML, sender, provider and the metadata
`{"source": "apt-server"}`. When `MAILLER_UNIX_SOCKET` is set the request goes
through that socket (same host deployment, the service user must be in the
group owning the socket).

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `EMAIL_BACKEND` | empty | `mailler` enables sending; anything else disables it |
| `MAILLER_URL` | `http://localhost` | Base URL of the mailler API |
| `MAILLER_UNIX_SOCKET` | empty | Unix socket of the mailler service |
| `MAILLER_CLIENT_ID` | empty | OAuth2 client for the `client_credentials` flow |
| `MAILLER_CLIENT_SECRET` | empty | Matching secret, also read from systemd credentials |
| `MAILLER_AUTH_URL` | empty | Token endpoint base; the OAuth2 issuer when empty |
| `MAILLER_PROVIDER` | `brevo` | Provider name sent to mailler |
| `EMAIL_FROM` | a noreply address | Sender address |
| `EMAIL_FROM_NAME` | `APT Server` | Sender name |

## Dependencies

`mrml` (MJML compiler) is added by this feature.

## Tests

- pytest: `tests/test_mailler.py` (token flow and reuse, payload, disabled
  backend, missing credentials, authentication and send failures, Unix socket
  transport), `tests/test_email.py` (template compilation, caching, missing
  template, delivery and skipping) and three more cases in
  `tests/test_dashboard.py` (who is notified), with mailler replaced by
  `httpx.MockTransport` or a recording function.
- behave: `features/share_notifications.feature` with the scenarios "Sharing
  with an email address sends a notification", "Sharing with an opaque
  identifier sends nothing", "Notifications are off when the email backend is
  not configured" and "A mailler outage never blocks sharing".
