# Step-CA root certificate

Certificates are issued by an internal PKI, [Step-CA](https://smallstep.com/docs/step-ca).
This feature adds the client that talks to it and the first VPN endpoint:
clients download the root certificate they must trust. It is also the first
route protected by the scopes of the OAuth2 feature.

## What it does

- `vpn_portal.core.stepca.StepCAClient` is the portal's Step-CA client.
  At this stage it can read the provisioner password, load the local root
  certificate and fetch the root certificate from the CA. The certificate
  signing and revocation methods arrive with the next feature. A shared
  instance, `stepca_client`, is used by the routes.
- The provisioner password comes from `STEPCA_PROVISIONER_PASSWORD` (or the
  systemd credential of the same name) first, then from the file named by
  `STEPCA_PROVISIONER_PASSWORD_FILE`. If neither exists the client raises
  `StepCAError`.
- Fetching the root certificate computes the SHA-256 fingerprint of the
  **local** root certificate (`STEPCA_ROOT_CA`), then requests
  `<STEPCA_URL>/root/<fingerprint>` over TLS verified with that same file.
  The PEM returned by the CA and the fingerprint are given back.
- `vpn_portal.api.deps.RequireVPNConnect` is a FastAPI dependency
  requiring the `vpn:connect` scope (checked through token exchange when it
  is configured).

## Endpoints

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/api/v1/vpn/ca` | GET | `vpn:connect` | Root CA certificate (PEM) and its SHA-256 fingerprint |

Response:

```json
{"ca_certificate": "-----BEGIN CERTIFICATE-----...", "fingerprint": "<64 hex characters>"}
```

Errors: `401` without a valid token, `403` without the `vpn:connect` scope,
`502` when the CA cannot be reached or answers with an error (the detail is
logged, not returned).

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `STEPCA_URL` | `https://127.0.0.1:8443` | Step-CA base URL |
| `STEPCA_ROOT_CA` | `/etc/step-ca/certs/root_ca.crt` | Local copy of the root certificate, used for TLS verification and the fingerprint |
| `STEPCA_PROVISIONER` | `vpn-portal` | JWK provisioner used to sign certificates |
| `STEPCA_PROVISIONER_PASSWORD` | empty | Provisioner password (secret) |
| `STEPCA_PROVISIONER_PASSWORD_FILE` | `/etc/step-ca/secrets/vpn-portal-password` | File holding the password, read when the variable is empty |

## Data model

None.

## Tests

- pytest: `tests/test_stepca.py` (configuration, password sources, local
  root certificate and fingerprint, root retrieval through a mocked HTTP
  transport, error mapping) and `tests/test_vpn_ca_endpoint.py` (the route:
  success, `502`, `401`, `403`, OpenAPI).
- behave: `features/stepca.feature` with the scenarios *Get root CA
  certificate successfully*, *Get root CA certificate when Step-CA is
  unavailable*, *Get root CA certificate without authentication*, *Get root
  CA certificate with insufficient scope*, *The fingerprint is computed from
  the local root certificate* and *A missing local root certificate is
  reported*. The CA is replaced by a mock; no Step-CA is running.
