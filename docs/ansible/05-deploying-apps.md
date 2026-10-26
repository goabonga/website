# Deploying applications

The `apps` playbook deploys the applications of this repository with the
[python_app](roles/python_app.md) role. Three variables drive it:

| Variable | Role |
| --- | --- |
| `website_apps_enabled` | The applications to deploy. |
| `website_apps_overrides` | What differs from the catalog, per component. |
| `website_secrets` | The secret values ([Secrets](03-secrets.md)). |

```yaml
website_domain: example.com
website_apps_enabled: [frontend, backend, auth]
```

## The catalog

`website_apps_catalog` describes the 16 applications of the platform as
**components**: one component is one systemd unit (or one set of wrapper
scripts). An application has a primary component named like it, and optional
workers, beats and scripts that run the same code:

| Application | Units | Host | Database | Required secrets |
| --- | --- | --- | --- | --- |
| `analytics` | `analytics` (gunicorn) | `ua.example.com` | `analytics` | - |
| `apt_server` | `apt-server` (gunicorn) | `apt.example.com` | `apt_server` | `MAILLER_CLIENT_SECRET`, `OAUTH2_CLIENT_SECRET`, `SESSION_SECRET`, `WEBHOOK_SECRET` |
| `asterisk` | `asterisk-bot` (audiosocket) | - | `application` | `OPENAI_API_KEY` |
| `auth` | `auth` (gunicorn), `auth-beat` (celery beat), `auth-worker` (celery worker) | `auth.example.com` | `auth` | `JWKS_ENCRYPTION_KEY`, `MAILLER_CLIENT_SECRET` |
| `backend` | `backend` (gunicorn), `backend-beat` (celery beat), `backend-worker` (celery worker) | `api.example.com` | `application` | `OAUTH2_CLIENT_SECRET`, `OPENAI_API_KEY` |
| `billing` | `billing` (gunicorn), `billing-beat` (celery beat), `billing-worker` (celery worker) | `billing.internal` | `billing` | `OAUTH2_CLIENT_SECRET`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |
| `custom_domain` | `custom-domain` (gunicorn), `custom-domain-beat` (celery beat), `custom-domain-worker` (celery worker) | `custom-domain.internal` | `custom_domain` | `OAUTH2_CLIENT_SECRET` |
| `frontend` | `frontend` (gunicorn) | `example.com` | - | - |
| `internal` | `internal` (gunicorn), `internal-worker` (celery worker) | `admin.internal` | `application` | `OAUTH2_CLIENT_SECRET`, `OPENAI_API_KEY`, `SECRET_KEY` |
| `knowledge` | `knowledge` (gunicorn), `knowledge-beat` (celery beat), `knowledge-worker` (celery worker) | `knowledge.example.com` | `knowledge` | `BILLING_WEBHOOK_SECRET`, `MAILLER_CLIENT_SECRET`, `OAUTH2_CLIENT_SECRET`, `OPENAI_API_KEY` |
| `mailler` | `mailler` (gunicorn), `mailler-beat` (celery beat), `mailler-worker` (celery worker) | `mailler.internal` | `mailler` | `BREVO_API_KEY`, `OAUTH2_CLIENT_SECRET`, `WEBHOOK_HMAC_SECRET` |
| `mta_sts` | `mta-sts` (gunicorn) | `mta-sts.example.com` | - | - |
| `reachy_mini_api` | `reachy-mini-api` (gunicorn) | `reachy.internal` | - | `OAUTH2_CLIENT_SECRET` |
| `team` | `team` (gunicorn), `team-beat` (celery beat), `team-worker` (celery worker) | `team.internal` | `team` | `OPENAI_API_KEY` |
| `vpn_portal` | `vpn-portal` (gunicorn), `vpn-portal-openvpn` (script) | `vpn.example.com` | `vpn_portal` | `OAUTH2_CLIENT_SECRET`, `OPENVPN_OAUTH2_CLIENT_SECRET`, `STEPCA_PROVISIONER_PASSWORD` |
| `webhooks` | `webhooks` (gunicorn) | `webhooks.example.com` | - | `OAUTH2_CLIENT_SECRET` |

(`example.com` stands for `website_domain`; `.internal` hosts are served on
`website_internal_listen` and registered in dnsmasq.)

The catalog holds no domain and no secret. Host names come from
`website_domain` and `website_hostnames` ([Configuration](02-configuration.md)),
secrets from `website_secrets`. For every component the catalog also sets the
database, the Alembic migrations, the unit type, the queues, the groups needed
to reach other applications' sockets, the fail2ban routes of `auth` and the
environment variables the application documents as having a sensible default.
Read `defaults/main/catalog.yml` of the role for the exact content.

Dependencies between applications are not resolved for you. `auth` sends mail
through `mailler`, `internal` and `webhooks` call `mailler` and `billing`
sockets, `team` calls `auth` and `analytics`: enable the applications that
others depend on, or override the setting (see below). An application whose
`extra_groups` names a group that does not exist yet is deployed anyway, and
the missing groups are reported; run the playbook again once they exist.

## Choosing what runs

- `website_apps_enabled` selects applications; each brings all its enabled
  components. A name that is not in the catalog stops the run and lists the
  known ones.
- `website_apps_limit` restricts one run to a subset of the enabled
  applications, which is how a single application is redeployed:

```bash
ansible-playbook goabonga.website.apps -e '{"website_apps_limit": ["backend"]}'
```

- Turn off one component of an application with an override:

```yaml
website_apps_overrides:
  auth_beat:
    enabled: false
```

## Overriding the catalog

`website_apps_overrides` is deep-merged over the catalog, keyed by component:
dictionaries are merged key by key, lists and scalars are replaced. The result
is merged over the component defaults. Only write what differs.

```yaml
website_apps_overrides:
  # More workers, and an environment variable
  backend:
    gunicorn:
      workers: 4
    env_vars:
      LOG_LEVEL: DEBUG
  # Another queue for the worker (a list is replaced, not appended to)
  backend_worker:
    celery:
      queues: [backend, reports]
      concurrency: 8
  # A wildcard certificate for the tenants of auth
  auth:
    nginx:
      ssl_wildcard: true
      ssl_wildcard_domains: ["*.auth.example.com"]
      ssl_dns_provider: route53
      dns_wildcard_cname_target: example.com
  # Listen on a TCP port instead of a socket
  mta_sts:
    gunicorn:
      socket: false
      port: 8010
```

The same mechanism defines components the catalog does not know:

```yaml
website_apps_overrides:
  backend_exports:
    app: backend
    type: daemon
    daemon:
      module: backend.exports
    env_vars:
      LOG_LEVEL: INFO
```

`app` attaches the component to an application. The unit is named after the
entry (`backend-exports`), uses the application's account and release, and
needs `postgres.database` if it wants `DATABASE_URL`. The full list of keys is
in the [component reference](roles/python_app.md#component-reference).

To deploy something that is not in the catalog at all, define
`website_apps_catalog` yourself; the role does not care where the components
come from.

## Environment and secrets

- `env_vars` is the content of the environment file. It is merged over the
  variables the role generates: `DATABASE_URL` (from `postgres`) and the
  `OAUTH2_*` variables (from `oauth2` and `website_oauth2_clients`).
  Lists and dictionaries are written as JSON.
- Secrets never go there. A component lists the names it needs in
  `secret_names` and `optional_secret_names`, you provide the values in
  `website_secrets`, and the application reads them from
  `$CREDENTIALS_DIRECTORY` ([Secrets](03-secrets.md)).
- OAuth2 client identifiers (public) are given once per application in
  `website_oauth2_clients`:

```yaml
website_oauth2_clients:
  backend:
    client_id: backend-api
    swagger_client_id: backend-swagger
```

## Releases and versions

The repository is cloned once per host, in `/var/lib/website/repo`. A release
is a commit of it, extracted in `/opt/<app>/releases/<commit>`; `current`
points to the active one.

| `version` | Meaning |
| --- | --- |
| not set | `website_repo_version` (default `main`): the tip of the branch at every run |
| a branch | the tip of that branch at every run |
| `backend-v1.4.0` | the tag created by the release of that application |
| a commit | exactly that commit |

Pin a version on the primary component of the application:

```yaml
website_repo_version: main
website_apps_overrides:
  backend:
    version: backend-v1.4.0
  auth:
    version: auth-v2.0.1
```

Releases are tagged per application (`<app>-vX.Y.Z`), so each application is
upgraded independently. Run the `apps` playbook after changing a version.

**Rollback**: set `version` back to the previous tag and run the playbook. The
old release is extracted again if it was pruned (`website_keep_releases`
controls how many stay on disk), the dependencies are re-synced and the units
restart. Database migrations are not reverted; a rollback across a migration
needs the matching `alembic downgrade`, run by hand.

**Private repository**: set `website_repo_token` (from the vault). It is used in
the HTTPS URL for the clone only.

## What a deployment does to a unit

1. Extract the release, point `current` to it, `uv sync --frozen --no-dev`.
2. Write the environment file and the credentials.
3. Run the `build_commands` (once per release), then the migrations.
4. Write the unit, start it, restart it if anything above changed.

The web client of `frontend` is built this way: the catalog sets
`build_node: true` and the commands `npm ci` and `npm run build` in
`apps/frontend/web`, and nginx serves `apps/frontend/web/dist` under `/static`.

A web component answers its health probe on `/health` before systemd considers
it started, and nginx exposes that path to the loopback address only.

## Integrations

| Component setting | Effect |
| --- | --- |
| `nginx.enabled` | Virtual host, certificate, access and error logs. |
| `nginx.internal_domain` | Listens on the internal address and registers the name in dnsmasq; with `ssl: step-ca` the certificate comes from the private CA. |
| `fail2ban.routes` | A jail per route on the nginx access log. |
| `sudoers` | Commands the account may run as root, for the custom domain provisioning of `auth`, `knowledge` and `custom_domain` workers. |
| `type: audiosocket` / `fastagi` with `asterisk.enabled` | A dialplan context included from `extensions.conf`. |
| `type: script` with `openvpn` | Wrapper scripts and the hooks of the OpenVPN server. |
| `ses_webhook` | SNS topics and SES notifications that call the endpoint. |

## Operating

```bash
systemctl status backend backend-worker backend-beat
journalctl -u backend -f
tail -f /opt/backend/logs/backend-error.log /opt/backend/logs/nginx/backend-access.log
```

- Logs of the units go to `/opt/<app>/logs`, rotated daily (14 files kept).
- Databases that are not shared are dumped every night to
  `/opt/<app>/backups` and kept for 7 days.
- `--check --diff` shows configuration changes. It does not simulate the
  checkout and the dependency installation.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `Unknown applications in website_apps_enabled` | Misspelled name; the message lists the valid ones. |
| `The secret X of Y is required` | Missing entry in `website_secrets`. |
| `nginx.domain or website_hostnames ... must be set` | `website_domain` is empty. |
| `nginx is not installed` or `certbot is not installed` | Run `site.yml` first. |
| `version ... not found` | Misspelled tag, or the tag does not exist in `website_repo_url`. |
| The unit restarts in a loop | `journalctl -u <unit>`: usually a missing secret or an unreachable database. |
| `Skipping the groups ...` | The application that owns the socket is not deployed yet; run again after it. |
