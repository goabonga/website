# Onboarding an application

Mailler serves several applications at once. This page is the checklist to
connect a new one, and the reference for what keeps the applications apart.
It only uses the features described on the previous pages.

## 1. An OAuth2 client for the application

The application authenticates with its own OAuth2 client at the identity
provider and sends the bearer token it obtains to Mailler. A backend process
normally uses the client credentials flow; a request made on behalf of a user
carries the token of the client that user logged in with.

- Mailler identifies the application by the `client_id` claim of the token
  (or `azp` when the claim is absent). A token with neither is refused.
- **Every OAuth2 client an application sends with must be registered** (step
  2): its web client and its backend client are two clients for Mailler.
- Scopes to grant to the client at the identity provider:

| Scope | Needed for |
| --- | --- |
| `mailler:send` | `POST /send`, `POST /schedule`, starting campaigns |
| `mailler:read` | Reading its emails, templates, contacts and campaigns (for example `GET /emails/{id}`) |
| `mailler:write` | Uploading templates through the API, managing contacts, groups and campaigns |
| `mailler:stats` | Its own statistics |

The administration scope (`ADMIN_SCOPE`, `mailler:admin` by default, or a
wildcard such as `mailler:*`) is for operators and lets a caller cross the
client boundary. Do not give it to an application.

## 2. Register the client

An operator registers the application, with the identity it sends with:

```bash
mailler clients register my-application \
  --name "My application" \
  --from-email no-reply@my-application.example --from-name "My application" \
  --allowed-provider brevo --default-provider brevo \
  --daily-quota 5000 --rate-limit-per-minute 60 \
  --callback-url https://my-application.example/mailler/status \
  --callback-secret-file /etc/my-application/mailler-callback-secret
```

or `POST /api/v1/clients` with the administration scope. Only the client id is
required, but a client can only send once it has a default sender and a
provider (or names them in every request). See
[authorized clients](15-authorized-clients.md), [limits](16-client-limits.md)
and [callbacks](20-status-callbacks.md). Providers must be configured on the
service (API key, region, host, ...): the registry only decides which client
may use which.

An unregistered or deactivated client gets `403` on every call;
`mailler clients deactivate` stops an application at once (within
`CLIENT_CACHE_TTL`), including the emails it already queued.

## 3. Provide the templates

The application owns its templates; Mailler ships none. Either upload them with
the [template API](08-templates.md) (`mailler:write`) or let the deployment
import a directory of `<slug>.mjml` / `<slug>.json` files:

```bash
mailler templates import --client-id my-application ./mailler-templates
```

Slugs are private to the application (two applications can both have
`welcome`) and may contain underscores. Re-running the import updates the
templates, so it can be part of every deployment.

## 4. Send

A transactional email is one call:

```http
POST /api/v1/send
Authorization: Bearer <token>
Idempotency-Key: invitation-42

{"to_email": "newcomer@example.com",
 "template_slug": "workspace_invitation",
 "variables": {"inviter": "Ann", "workspace": "Acme", "link": "https://..."},
 "metadata": {"invitation": 42}}
```

The sender, the reply-to and the provider come from the record
([rules](15-authorized-clients.md)); the template is rendered by Mailler
([details](18-template-sending.md)); repeating the request with the same
`Idempotency-Key` ([details](19-idempotency.md)) never sends a second email.
An application that prefers to render itself sends `subject` and
`html_content` instead.

## 5. Follow the status

Either read `GET /api/v1/emails/{id}` (`mailler:read`), or give the client a
callback and let Mailler post a signed notification when the email is sent,
delivered, bounced or fails ([status callbacks](20-status-callbacks.md)).

## What keeps the applications apart

| Data | Rule |
| --- | --- |
| Emails (`/emails`), statistics (`/stats`) | Only the caller's own; another client's email is `404` |
| Templates | Private to the client, slug unique per client, edited and deleted by the owner only |
| Contacts, contact groups, campaigns | Private to the client; the same address can be a contact of several clients; a campaign only uses the template and group of its client, and an unsubscribe link only unsubscribes the contact of the client that sent the email |
| Sender, provider, reply-to | Forced or validated from the record: no arbitrary `from_email` |
| Volume | Optional per-client rate limit and daily quota |
| Inbound mailbox | Shared by the platform, readable with the administration scope only |
| Registry | Administration scope only |

Administrators see and manage every client (`client_id` query parameter on the
list routes). The shared infrastructure is not separated: the providers and
their keys, the Celery queue and the database are common to all clients.

## Upgrading an existing installation

A database created before the data belonged to clients is brought up to date
by migration `006` ([authorized clients](15-authorized-clients.md)): set
`LEGACY_CLIENT_ID` to the client that owns the existing templates, contacts and
campaigns before running it, then register every application that sends, since
unregistered clients are refused.

## What is not verified

The migrations and the whole test suites run on SQLite and mocks: no run was
made against PostgreSQL, a real Brevo or SES account, a real identity
provider, or a Unix socket in production. See [deployment](21-deployment.md)
for the transport the processes use.
