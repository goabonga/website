# OpenVPN hook scripts

The application ships a helper script, `apps/vpn-portal/scripts/openvpn.py`,
that runs on the OpenVPN server host and connects the VPN server to the
portal's [internal API](06-internal-api.md). It is not part of the
`vpn_portal` package and not served by the web application: it is deployed
next to OpenVPN, in its own virtual environment, which only needs `httpx`
(`apps/vpn-portal/requirements-openvpn.txt`).

## What it does

One script, three modes selected by a flag, each one wired to an OpenVPN
directive:

| Flag | OpenVPN directive | Behaviour |
| --- | --- | --- |
| `--connect` | `client-connect` | Validates the certificate with `/api/v1/internal/validate`, appends `push "route <network> <netmask>"` lines for the returned routes to the temporary configuration file OpenVPN passes as the last argument, then records the connection with `/api/v1/internal/connect`. Exit code `1` (connection refused) when the common name is missing, the API does not answer `200` or the certificate is not valid. A failure of the final `connect` call is only logged. |
| `--disconnect` | `client-disconnect` | Reads `bytes_received` and `bytes_sent` and records them with `/api/v1/internal/disconnect`. |
| `--reneg` | `tls-verify` | Called at every TLS renegotiation. Certificates of the CA chain (depth above 0) are accepted. For the client certificate (depth 0) it validates again; if the certificate has been revoked or has expired, or the API answers with an error, the client is killed and the exit code is `1`. If the API cannot be reached the client is kept (fail open). |

OpenVPN passes the client data in lowercase environment variables
(`common_name`, `untrusted_ip`, `untrusted_port`, `ifconfig_pool_remote_ip`,
`bytes_received`, `bytes_sent`) and, for `tls-verify`, `X509_0_CN`.

Because the portal issues certificates that live 10 to 15 minutes, the
`--reneg` mode is what ends sessions: with `reneg-sec` set to a few minutes,
a certificate that has expired or has been revoked (by the user, by an
administrator through the [admin API](07-admin-api.md)) is refused at the
next renegotiation and the client is cut off.

### Killing a client

OpenVPN removes the common name of a rejected client from its table but keeps
the data channel open, so `kill <common name>` does not work. The script
therefore kills by real address (`kill <ip>:<port>`) through the OpenVPN
management interface. OpenVPN is single-threaded and blocked while the
script runs, so connecting from the script itself would deadlock: the script
forks a detached child that waits two seconds, connects to the management
interface, sends the `kill` command and logs the outcome to syslog.

### Authentication and token cache

The script authenticates to the portal as a machine client with the OAuth2
`client_credentials` grant (scope `vpn:server`). The access token is cached in
a JSON file (mode `0600`) and reused until 30 seconds before it expires, so that OpenVPN
events do not each trigger a call to the OAuth2 server. If the client
settings are missing or the token request fails, the script logs an error
and exits with `1`.

The client secret is read from the systemd credential
`$CREDENTIALS_DIRECTORY/OPENVPN_OAUTH2_CLIENT_SECRET` first and from the
environment otherwise.

### Logging

Records go to syslog (`daemon` facility, `INFO` and above, prefixed
`vpn-portal-openvpn:`), which is where OpenVPN logs, and to stderr
(`WARNING` and above, or everything when the `DEBUG` variable is set).

## OpenVPN configuration

```
script-security 2
management 127.0.0.1 7505
client-connect /opt/vpn-portal-openvpn/bin/openvpn-connect
client-disconnect /opt/vpn-portal-openvpn/bin/openvpn-disconnect
tls-verify /opt/vpn-portal-openvpn/bin/openvpn-reneg
reneg-sec 300
```

where each wrapper is a small executable that runs `openvpn.py` with the
matching flag (`--connect`, `--disconnect`, `--reneg`); the paths above are
examples. The management
interface must listen on the loopback address only.

## Settings

Environment variables read by the script (not by the web application):

| Variable | Default | Description |
| --- | --- | --- |
| `OPENVPN_OAUTH2_CLIENT_ID` | empty | OAuth2 client identifier |
| `OPENVPN_OAUTH2_CLIENT_SECRET` | empty | OAuth2 client secret (secret, see above) |
| `OPENVPN_OAUTH2_TOKEN_URL` | empty | Token endpoint of the OAuth2 server, for example `https://auth.example.com/oauth2/token` |
| `OPENVPN_OAUTH2_SCOPE` | `vpn:server` | Scope requested |
| `OPENVPN_API_BASE_URL` | `http://127.0.0.1:8000` | Base URL of the portal |
| `OPENVPN_TOKEN_CACHE_PATH` | `/var/run/vpn-portal/token.json` | Token cache file |
| `OPENVPN_MANAGEMENT_HOST` | `127.0.0.1` | Management interface host |
| `OPENVPN_MANAGEMENT_PORT` | `7505` | Management interface port |

The OAuth2 client must be allowed the `client_credentials` grant and the
`vpn:server` scope. These variables are read when the script starts.

## Data model

None. The script keeps no state other than the token cache file.

## Tests

- pytest: `tests/test_openvpn_script.py`, which imports the script as
  `scripts.openvpn` (the pytest configuration adds the application directory
  to the Python path): credentials, token cache and token request, route
  writing and netmask conversion, the three handlers with their failure
  modes, the management kill (fork replaced by a mock) and the entry point.
- behave: `features/hooks.feature` runs the real script against the real
  portal application: the script's HTTP client is given a transport that
  serves each request in-process through the ASGI application, backed by the
  in-memory database, and the OAuth2 server is a mock. Scenarios: *A valid
  certificate is allowed to connect and its routes are pushed*, refusal of
  revoked, expired and unknown certificates and of an event without common
  name, *Disconnection records the traffic*, renegotiation of valid and
  revoked certificates, *Certificates of the CA chain are not checked*, the
  token request and cache, and the netmask conversion. The management kill
  itself is mocked; no OpenVPN server is involved.
