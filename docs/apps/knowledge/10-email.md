# Email delivery

The service sends transactional emails (workspace invitations and the workspace
deletion life cycle) through the platform's **mailler** service, and only through it:
there is no SMTP backend and no rendering pipeline in this application. Knowledge ships
the MJML sources of its five emails, mailler stores them for the OAuth2 client of
knowledge, renders them and delivers them with the sender and the provider of that
client's registration. Nothing is sent automatically yet; the background tasks and the
web interface that use these building blocks come with later features.

## The templates

The sources are files of the package, in `knowledge/templates/emails/`: two files per
template, named after its slug.

| Slug | Sent when |
| --- | --- |
| `workspace_invitation` | Someone is invited to a workspace |
| `workspace_deletion` | The owner asks for the deletion and must confirm it |
| `workspace_deletion_reminder` | One day before a scheduled deletion |
| `workspace_deletion_scheduled` | The deletion is confirmed and scheduled |
| `workspace_deleted` | The workspace is permanently deleted |

- `<slug>.mjml` is the MJML source. Its placeholders are Jinja2 `{{ variable }}`
  expressions, rendered by mailler with HTML auto-escaping (the former `%variable%`
  syntax is not understood by mailler in the HTML).
- `<slug>.json` is the description mailler reads: `name`, `description` and the
  `subject_template`, which is a template too (`You're invited to join {{ workspace_name }}
  on Knowledge`). The subjects are therefore part of the template, not of the code.

Every template uses `workspace_name`, `user_email` and `year`; the others are
`inviter_name`, `role` and `invitation_url` (invitation), `confirmation_url` (deletion),
`deletion_date` and `cancel_url` (reminder), `deletion_date` (scheduled) and `support_url`
(deleted).

`knowledge.email_templates` locates the directory (`TEMPLATES_DIR`, `template_slugs()`
and a constant per slug) and prints it when run as a module. The deployment imports the
directory into mailler with the `mailler` command, for the OAuth2 client of knowledge,
and can run it again at every deployment (the import creates or updates):

```bash
mailler templates import --client-id <knowledge OAuth2 client id> \
    "$(python -m knowledge.email_templates)"
```

Mailler compiles the MJML when it imports it (nothing is written if one template does not
compile; `--dry-run` only checks). The five templates were compiled and rendered with
the code of mailler (`mailler.services.mjml` and `mailler.services.rendering`) while this
page was written; see the platform onboarding page for the registration of the client.

## Sending

`knowledge.services.mailler.MaillerClient.send_template(template_slug, to_email, variables,
to_name=None, idempotency_key=None, metadata=None)` posts to `<MAILLER_URL>/api/v1/send`
(or to the Unix socket `MAILLER_SOCKET_PATH`, which takes precedence) with a bearer token
and the body `{"to_email", "template_slug", "variables"}`. It does not name a sender, a
reply-to, a provider or a subject: mailler takes them from the registration of the client
(the application cannot choose another sender than the ones the operator allowed).

- **Authentication.** The token is obtained with the OAuth2 client-credentials grant for the
  scope `mailler:send` (`knowledge.services.service_auth`, shared with billing). The client is
  `MAILLER_CLIENT_ID`/`MAILLER_CLIENT_SECRET`, or `OAUTH2_CLIENT_ID`/`OAUTH2_CLIENT_SECRET`
  when those are empty. Mailler identifies the application by the `client_id` of the token,
  so this client must be the one registered in mailler. A `401` renews the token once.
- **Idempotency.** `idempotency_key` becomes the `Idempotency-Key` header: mailler never
  sends two emails for the same key, it answers with the first one. The tasks use the key to
  make their retries safe.
- **Result.** `SendResult(id, status, message, task_id, missing_variables)`. A template
  variable the call did not provide renders empty and is listed in `missing_variables`; the
  email is still sent, and the client logs a warning that names the template and the
  variables.
- **Errors.** Everything else raises `MaillerError(detail, status_code, retryable)`:

| Answer | Meaning | `retryable` |
| --- | --- | --- |
| `403` | The client is not registered, is deactivated, or the sender/provider is not allowed | no |
| `404` | The template is not imported for this client (the deployment forgot the import) | no |
| `422` | The template is not active or cannot be rendered, or the body is invalid | no |
| `429` | The rate limit or the daily quota of the client is reached | yes |
| `5xx`, `408`, `425` | Mailler is failing | yes |
| network error, token server failing | Mailler or the OAuth2 server cannot be reached | yes |
| nothing configured, bad credentials | `MAILLER_URL`/`MAILLER_SOCKET_PATH` or the OAuth2 client is missing | no |

`get_mailler_client()` returns a process-wide client.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `MAILLER_URL` | empty | HTTP base URL of the mailler service. |
| `MAILLER_SOCKET_PATH` | empty | Unix socket of the mailler service; takes precedence over the URL. |
| `MAILLER_CLIENT_ID` | empty | OAuth2 client registered in mailler; empty means `OAUTH2_CLIENT_ID`. |
| `MAILLER_CLIENT_SECRET` | empty | Its secret (a secret, systemd credential or variable); empty means `OAUTH2_CLIENT_SECRET`. |
| `MAILLER_MAX_RETRIES` | `3` | Retries of an email task after a failure that can pass. |
| `MAILLER_RETRY_DELAY` | `60` | Seconds before the first retry, doubled each time. |
| `SERVICE_TIMEOUT` | `10.0` | Seconds before a call to mailler (or to the token endpoint) times out. |

The `mrml`, `beautifulsoup4` and SMTP code of the original application are gone: the
service has no SMTP setting, no sender address and no default provider of its own.

## Tests

pytest:

- `unit/test_mailler_service.py`: the configuration (URL, socket, timeout), the request
  (slug, variables, token for `mailler:send`, no sender fields, idempotency header, request
  on the wire), the token renewal, the missing variables and every refusal with its
  `retryable` flag.
- `unit/test_email_templates.py`: the five templates and their descriptions are valid for the
  `mailler templates import` command, use the Jinja2 syntax and the common variables, and the
  module prints the directory.

behave (`features/email.feature`): the templates are the shipped files, mailler and the OAuth2
server are fakes.

- Every shipped template can be imported into mailler (outline over the five templates)
- The import command is given the template directory
- An email is sent from a template of the application
- Variables the template needed but did not get are reported
- Mailler refuses the email (outline over 403, 404, 422, 429 and 503)
- Mailler cannot be reached
- Mailler is not configured

Not verified: no real mailler service, provider or OAuth2 server was used, and the
`mailler templates import` command was not run against a database.
