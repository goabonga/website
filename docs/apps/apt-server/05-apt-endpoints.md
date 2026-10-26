# APT client endpoints

The HTTP surface read by `apt`: the `dists/` metadata, the `pool/` downloads
and the repository public key. Credentials are resolved for every request and
the three access layers are applied to it.

## Endpoints

| Endpoint | Description |
| --- | --- |
| `GET /dists/{suite}/Release` | Per-caller `Release` (see the APT indexes page) |
| `GET /dists/{suite}/InRelease` | Clear-signed `Release` (plain `Release` when unsigned) |
| `GET /dists/{suite}/Release.gpg` | Detached signature; 404 when no signing key is configured |
| `GET /dists/{suite}/{component}/binary-{arch}/Packages` | Per-caller `Packages` index |
| `GET /dists/{suite}/{component}/binary-{arch}/Packages.gz` | Gzip variant (`application/gzip`) |
| `GET /pool/{component}/{prefix}/{name}/{filename}` | Package download |
| `GET /pubkey.gpg` | Public key of `APT_GPG_KEY_ID` (`application/pgp-keys`) |

All of them are hidden from the OpenAPI schema. Unknown suites, components or
architectures (other than `all`) return 404.

### Authentication

`apt` can only send `Authorization: Basic`, so `apt_server.services.apt_auth`
resolves a `Caller` from:

- `Basic <user>:<token>`: the username is informational, the password is the
  credential.
- `Bearer <token>`: for API style clients.

A credential with three dot-separated segments is validated as a JWT
(signature and introspection), anything else as an opaque personal access
token (introspection only). No credentials means an anonymous caller, which
is valid for public components. Invalid or revoked credentials answer
`401` with `WWW-Authenticate: Basic realm="apt", charset="UTF-8"`, and `503`
is returned when OAuth2 is not configured. The caller gets its `sub`, scopes
(`scope` or `scopes` claim), groups (`groups` or `roles` claim), the email as
display name and a name.

A client configuration looks like this (placeholders only):

```
deb [signed-by=/etc/apt/keyrings/example.gpg] https://apt.example.com stable main
```

with credentials in `/etc/apt/auth.conf.d/` (`machine apt.example.com login
<any> password <personal access token>`).

### Access layers applied

1. Layer 1: the component must be known; a non-public component needs a
   caller (otherwise 401).
2. Layer 2: identity and scopes from the credential.
3. Layer 3: indexes only contain packages the caller can see, and a pool
   request is answered only if `can_read` allows it. A package that does not
   exist and a package the caller may not read both return 404, so existence
   is not disclosed.

### Downloads

The `.deb` body never goes through Python. The route looks the package up by
its pool path and replies `200` with an empty body, `X-Accel-Redirect:
<APT_INTERNAL_PREFIX>/<pool path>`, `Content-Type: application/octet-stream`
and `Cache-Control: no-cache`. nginx must expose an `internal` location of
that prefix aliased to `APT_REPO_ROOT`, for example:

```nginx
location /_internal/ {
    internal;
    alias /var/lib/apt-server/;
    sendfile on;
}
```

### Public key

`GET /pubkey.gpg` runs `gpg --armor --export <APT_GPG_KEY_ID>`. It answers
404 when no key is configured or the export fails or is empty.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `APT_INTERNAL_PREFIX` | `/_internal` | Prefix of the nginx `internal` location |

The suites, components, architectures and signing key come from the previous
features.

## Tests

- pytest: `tests/test_apt_auth.py` (header parsing, Basic and Bearer, JWT
  versus opaque, revoked, invalid, no subject, unconfigured OAuth2) and
  `tests/test_apt_routes.py` (indexes per caller, gzip, unknown values,
  private component challenge, `Release` and signatures with a stubbed signer,
  `X-Accel-Redirect`, hidden private packages, group grants, public key export
  with a stubbed `gpg`), over HTTP with a SQLite database.
- behave: `features/apt_endpoints.feature` with the scenarios "Anonymous
  clients fetch the public Packages index", "Release is served to anonymous
  clients", "Private components ask for credentials", "A personal access token
  opens the private component", "An unknown access token is refused", "Public
  packages are downloaded through nginx", "Private packages are hidden from
  other users", "Owners download their private packages", "Unknown suites are
  not found" and "The public key is not available without a signing key".
