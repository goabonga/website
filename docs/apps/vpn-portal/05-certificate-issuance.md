# Certificate issuance and lifecycle

This is the core of the portal: an authenticated user asks for a VPN bundle
and receives a short-lived client certificate, its private key and a
complete OpenVPN profile; they can later check their status or revoke the
certificate.

## What it does

- **Issuance** (`vpn_portal.services.certificate.CertificateService`):
  1. builds a unique common name `vpn-<user_id>-<unix timestamp>`;
  2. resolves the routes of the user (see below);
  3. generates a 2048-bit RSA key and a CSR in memory, with the e-mail as a
     SAN when the username contains an `@`;
  4. has Step-CA sign it (`StepCAClient.generate_certificate`, which runs
     `step ca sign` with the JWK provisioner; the duration is the requested
     one, `CERT_DEFAULT_DURATION_MINUTES` by default, capped at
     `CERT_MAX_DURATION_MINUTES`);
  5. records the certificate in `vpn_certificates` (serial, common name,
     validity, device name, scopes, routes);
  6. renders the OpenVPN profile.

  The private key is returned to the caller and never stored. Temporary
  files holding the CSR, the provisioner password and the signed
  certificate are deleted whatever the outcome.
- **Profile** (`vpn_portal.core.ovpn.generate_ovpn_config`): an inline
  `.ovpn` file with `remote <OPENVPN_SERVER> <OPENVPN_PORT>`, the protocol,
  `remote-cert-tls server`, AES-256-GCM / SHA-256 and the CA, certificate,
  key and `tls-auth` blocks (`key-direction 1`). The CA certificate is the
  local Step-CA root, the `tls-auth` key is read from `OPENVPN_TA_KEY_PATH`.
- **RBAC routes**: every user gets `DEFAULT_ROUTES`; each scope found in
  `SCOPE_ROUTES` (or its `resource:*` wildcard entry) adds its networks.
  The result is deduplicated and sorted. With the default mapping,
  `vpn:internal` adds `10.0.0.0/8`, `vpn:infrastructure` adds
  `192.168.0.0/16`, `vpn:development` adds `10.100.0.0/16` and
  `vpn:production` adds `10.200.0.0/16`.
- **Revocation**: marks the record revoked (`revoked_at`,
  `revocation_reason`) and asks Step-CA to revoke the serial (passive
  revocation). A Step-CA failure is logged and the database revocation
  still happens, so the portal never keeps accepting a certificate it
  believes revoked.

## Endpoints

All three require the `vpn:connect` scope.

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/vpn/connect` | POST | Issue a certificate and return the bundle |
| `/api/v1/vpn/disconnect` | POST | Revoke the caller's active certificate |
| `/api/v1/vpn/status` | GET | Tell whether the caller has an active certificate |

`POST /api/v1/vpn/connect` takes an optional JSON body:

```json
{"device_name": "laptop", "certificate_ttl": 600}
```

`certificate_ttl` is in seconds (60 to 900) and is converted to whole
minutes. The response contains `certificate`, `private_key`,
`ca_certificate`, `ovpn_config`, `expires_at`, `vpn_server`, `vpn_port` and
`assigned_routes`. Any failure while issuing (Step-CA down, missing
`tls-auth` key, ...) answers `500` with a generic message; the cause is
logged.

`POST /api/v1/vpn/disconnect` answers `{"status": "disconnected",
"revoked_at": ...}`, or `{"status": "not_connected", "revoked_at": null}`
when the user has no active (unexpired, unrevoked) certificate.

`GET /api/v1/vpn/status` answers `connected`, `certificate_serial`,
`common_name`, `expires_at` and `assigned_routes` of the most recent active
certificate.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CERT_DEFAULT_DURATION_MINUTES` | `10` | Lifetime when the client does not ask for one |
| `CERT_MAX_DURATION_MINUTES` | `15` | Hard ceiling on the lifetime |
| `OPENVPN_SERVER` | `vpn.example.com` | Host written in the profile |
| `OPENVPN_PORT` | `1194` | Port written in the profile |
| `OPENVPN_PROTO` | `udp` | Protocol written in the profile |
| `OPENVPN_CA_PATH` | `/etc/openvpn/server/ca.crt` | Declared for completeness; the portal itself does not read it (the profile embeds the Step-CA root) |
| `OPENVPN_TA_KEY_PATH` | `/etc/openvpn/server/ta.key` | `tls-auth` key embedded in the profile |
| `SCOPE_ROUTES` | see above | JSON object mapping scopes to CIDR lists |
| `DEFAULT_ROUTES` | `["10.8.0.0/24"]` | JSON list of routes granted to everyone |

Step-CA itself needs a provisioner limited to short lifetimes, for example:

```bash
step ca provisioner add vpn-portal --type JWK --create \
  --password-file=/etc/step-ca/secrets/vpn-portal-password \
  --x509-max-dur=15m --x509-default-dur=10m
```

The `step` binary is expected at `/usr/bin/step`.

## Data model

Uses the `vpn_certificates` table of the previous feature. Nothing is
added.

## Tests

- pytest: `tests/test_stepca_signing.py` (the `step` binary is replaced by
  a fake that writes a real certificate: command line, CSR content, SAN,
  duration capping, temporary file cleanup, failures),
  `tests/test_ovpn.py` (profile content and `tls-auth` loading),
  `tests/test_certificate_service.py` (common name, routes, persistence,
  revocation, active certificate lookup, on an in-memory session),
  `tests/test_vpn_endpoints.py` (the three routes, scope checks) and
  `tests/test_fake_session.py` (the in-memory session itself, which lives in
  `tests/fake_session.py`).
- behave: `features/vpn.feature` with the scenarios *Connect to VPN
  successfully*, *Connect to VPN with device name and custom TTL*, *Routes
  follow the scopes of the user*, *Connect to VPN fails when the
  certificate authority fails*, the unauthenticated and insufficient-scope
  cases, *Disconnect from VPN when connected*, *Disconnect from VPN when not
  connected*, *Revocation survives a certificate authority outage* and the
  two *Check VPN status* scenarios. Step-CA is a mock and the database an
  in-memory session; the SQL itself is not exercised without PostgreSQL.
