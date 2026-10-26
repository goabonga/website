# VPN Portal

Zero-Trust VPN service. Users authenticate with an OpenID Connect access
token, the portal checks their `vpn:*` scopes, asks the internal Step-CA for
a short-lived client certificate (10 to 15 minutes) and returns a ready-to-use
OpenVPN profile. The OpenVPN server reports back to the portal through hook
scripts, which lets the portal keep an audit trail and reject expired or
revoked certificates.

The application is the workspace member `apps/vpn-portal` (distribution
`vpn-portal`, import package `vpn_portal`). It is a FastAPI application
backed by PostgreSQL and Redis, plus a small set of helper scripts that run
next to the OpenVPN server.

```
User ----OIDC token----> VPN Portal ----CSR----> Step-CA
                              ^  |
         validate / connect / |  | certificate + .ovpn profile
         disconnect events    |  v
                         OpenVPN hooks <---- OpenVPN server <---- VPN client
```

## Features

The application is documented feature by feature, in the order in which
each feature builds on the previous ones.

1. [Application foundation](01-foundation.md): package, settings, logging and health check.
2. [OAuth2 authentication](02-oauth2-authentication.md): token validation, introspection, token exchange and scope checks.
3. [Certificate records and migrations](03-certificate-records.md): the PostgreSQL model of issued certificates and its Alembic migration.
4. [Step-CA root certificate](04-step-ca-root-certificate.md): the Step-CA client and the root CA endpoint.
5. [Certificate issuance and lifecycle](05-certificate-issuance.md): short-lived certificates, OpenVPN profile, RBAC routes, revocation and status.

## Testing

Each feature has pytest tests and a behave scenario file. Everything runs
in process: Step-CA, the OAuth2 server, Redis, PostgreSQL and the OpenVPN
server are replaced by fakes.

```bash
uv run --package vpn-portal --group dev pytest apps/vpn-portal
uv run --package vpn-portal --group dev behave apps/vpn-portal/features
```
