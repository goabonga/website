# Deployment

How `vpn-portal` runs in production. The production inventory and its
secrets are kept outside this repository; this page lists the processes, the
settings and the secrets they need, without any value. There are two
deployments from the same code base: the web API, and the hook scripts on
the OpenVPN server.

## Web API

- **Process**: `gunicorn vpn_portal.main:app` with the
  `uvicorn.workers.UvicornWorker` worker class, two workers, listening on a
  Unix socket. Gunicorn is a dependency of the package. Older deployments referenced the code as
  `app.main:app`; from this repository the import package is `vpn_portal`.
- **Reverse proxy**: nginx terminates TLS for the public domain of the
  portal and proxies to the socket. `/health` is the probe endpoint. The
  Swagger UI is served, with its public PKCE client.
- **User**: a dedicated system user, a member of the `step` group so that it
  can read the provisioner password file of Step-CA.
- **Unit**: a systemd service with the usual sandboxing options
  (`NoNewPrivileges`); stdout and stderr go to separate log files, which
  matches the logging split of the foundation feature.

### Data stores and dependencies

- **PostgreSQL**: one database owned by the service user, reached through
  the local socket (`DATABASE_URL=postgresql:///<database>`). Run the
  migrations on every release:
  `alembic -c apps/vpn-portal/alembic.ini upgrade head`. Back the database
  up: it is the audit trail of issued certificates and sessions.
- **Redis**: one logical database, for the introspection and token exchange
  caches (`REDIS_URL`).
- **Step-CA**, on the same host, with a JWK provisioner limited to short
  lifetimes (15 minutes at most). The portal answers `500` on `connect`
  and `502` on `ca` while Step-CA is down.
- **OAuth2 / OIDC server** (the `auth` application): JWKS discovery,
  introspection and token exchange; it must know the portal's confidential
  client and the `vpn:*` scopes.
- **OpenVPN server**, for the `tls-auth` key (`OPENVPN_TA_KEY_PATH`) that is
  embedded in the profiles; it must be readable by the service user, and
  deployed before the portal.

### Settings in production

The environment file of the service sets the variables documented on the
feature pages:

| Feature page | Variables |
| --- | --- |
| [Foundation](01-foundation.md) | `APP_NAME`, `DEBUG`, `DOCS_ENABLED`, `LOG_LEVEL` |
| [OAuth2 authentication](02-oauth2-authentication.md) | `OAUTH2_ISSUER`, `OAUTH2_SWAGGER_CLIENT_ID`, `OAUTH2_CLIENT_ID`, `OAUTH2_CLIENT_CACHE_TTL`, `TOKEN_INTROSPECTION_CACHE_TTL`, `JWKS_CACHE_TTL`, `OAUTH2_TRUSTED_ISSUERS`, `REDIS_URL`, `REDIS_KEY_PREFIX` |
| [Certificate records](03-certificate-records.md) | `DATABASE_URL`, `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_ECHO` |
| [Step-CA root certificate](04-step-ca-root-certificate.md) | `STEPCA_URL`, `STEPCA_ROOT_CA`, `STEPCA_PROVISIONER`, `STEPCA_PROVISIONER_PASSWORD_FILE` |
| [Certificate issuance](05-certificate-issuance.md) | `CERT_DEFAULT_DURATION_MINUTES`, `CERT_MAX_DURATION_MINUTES`, `OPENVPN_SERVER`, `OPENVPN_PORT`, `OPENVPN_PROTO`, `OPENVPN_TA_KEY_PATH`, `SCOPE_ROUTES`, `DEFAULT_ROUTES` |

Set `DEBUG` to `false` in production.

### Secrets

Two values are secrets and are never written in the environment file. They
are delivered with systemd credentials (encrypted with `systemd-creds`,
loaded with `LoadCredentialEncrypted`), which the application reads from
`$CREDENTIALS_DIRECTORY` before falling back to the environment:

- `STEPCA_PROVISIONER_PASSWORD` (the password file read through the `step`
  group is the alternative);
- `OAUTH2_CLIENT_SECRET`.

### Known mismatches

The example environment file of the original repository named the Redis
setting `OAUTH2_CLIENT_REDIS_URL`. The application does not read that name:
the caches use `REDIS_URL` and stay disabled while it is empty (one
introspection request per authenticated call). The original `pyproject.toml`
also listed `python-jose` while the code imports PyJWT; this repository
declares what the code imports.

## Hook scripts on the OpenVPN server

The script `apps/vpn-portal/scripts/openvpn.py` is deployed on the OpenVPN
host, in its own virtual environment built from
`apps/vpn-portal/requirements-openvpn.txt` (only `httpx`), by the same user
as the portal. No service is created: three executable wrappers
(`openvpn-connect`, `openvpn-disconnect`, `openvpn-reneg`) run the script with
`--connect`, `--disconnect` and `--reneg`, and are referenced from
`server.conf` (see [OpenVPN hook scripts](08-openvpn-hook-scripts.md)).

Points specific to this deployment:

- OpenVPN drops its privileges before running the hooks. The environment
  file the wrappers read must be readable by the group OpenVPN runs as, and
  must hold the non-secret settings (`OPENVPN_OAUTH2_CLIENT_ID`,
  `OPENVPN_OAUTH2_TOKEN_URL`, `OPENVPN_OAUTH2_SCOPE`, `OPENVPN_API_BASE_URL`,
  `OPENVPN_TOKEN_CACHE_PATH`, `OPENVPN_MANAGEMENT_HOST`,
  `OPENVPN_MANAGEMENT_PORT`).
- `OPENVPN_OAUTH2_CLIENT_SECRET` is a secret: provide it as an encrypted
  systemd credential on the OpenVPN unit (a drop-in with
  `LoadCredentialEncrypted=`), not in the environment file.
- The token cache directory must be writable by the user the hooks run as
  and be recreated at boot (it lives in a temporary filesystem, for example
  through `tmpfiles.d`).
- `script-security 2` and the `management` directive (loopback only) are
  required in `server.conf`; where AppArmor confines OpenVPN, the wrappers
  and the temporary route files must be allowed.
- Changing `server.conf` or the unit restarts OpenVPN and disconnects every
  client: deploy during a maintenance window.
- Choose `reneg-sec` with the certificate lifetime in mind: it is the
  longest time a client survives the revocation or expiry of its
  certificate.

## Ansible

The `ansible/` collection of this repository provides the surrounding
infrastructure: [step_ca](../../ansible/roles/step_ca.md) (including the
short-lived VPN portal provisioner and its password file readable by the
`step` group), [openvpn](../../ansible/roles/openvpn.md),
[postgres](../../ansible/roles/postgres.md),
[redis](../../ansible/roles/redis.md), [nginx](../../ansible/roles/nginx.md)
and [certbot](../../ansible/roles/certbot.md). It does not yet contain a
role that deploys this application or its hook scripts, so the service unit,
the environment files and the wrappers are currently installed by the
production inventory outside this repository.

## Local development

```bash
# optional local PostgreSQL (port 5443) and Redis (port 6390)
docker compose -f apps/vpn-portal/compose.yml up -d

export DATABASE_URL=postgresql://vpn_portal:vpn_portal@localhost:5443/vpn_portal_test
export REDIS_URL=redis://localhost:6390/0
uv run --package vpn-portal alembic -c apps/vpn-portal/alembic.ini upgrade head
uv run --package vpn-portal uvicorn vpn_portal.main:app --port 8000
```

The compose file only starts the two data stores (`postgres:16-alpine`,
database `vpn_portal_test`, and `redis:7-alpine`); its credentials are local
development values. The pytest suite and the behave scenarios do not need
it. Issuing real certificates additionally needs a Step-CA and the `step`
binary, and protected routes need an OAuth2 server.

## Verifying a deployment

```bash
curl -fsS https://<portal-domain>/health
systemctl status <portal-service>
journalctl -u <portal-service> -f
```
