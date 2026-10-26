# security.txt endpoint

Publishes the vulnerability disclosure file defined by
[RFC 9116](https://www.rfc-editor.org/rfc/rfc9116) so that security
researchers know where to report a problem.

## Endpoint

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/security.txt` | GET | `text/plain` document built from the settings; hidden from the OpenAPI schema |

The body is generated on every request by
`backend.routes.security_txt.generate_security_txt`. A field is written as
`Name: value` only when its setting is not empty, so an unconfigured service
answers `200` with an empty body.

## Settings

| Variable | Output field |
|----------|--------------|
| `SECURITY_CONTACT` | `Contact` (required by the RFC) |
| `SECURITY_EXPIRES` | `Expires` (required by the RFC, ISO 8601) |
| `SECURITY_ENCRYPTION` | `Encryption` |
| `SECURITY_ACKNOWLEDGMENTS` | `Acknowledgments` |
| `SECURITY_PREFERRED_LANGUAGES` | `Preferred-Languages` |
| `SECURITY_CANONICAL` | `Canonical` |
| `SECURITY_POLICY` | `Policy` |
| `SECURITY_HIRING` | `Hiring` |
| `SECURITY_CSAF` | `CSAF` |

All of them default to an empty string. Fields are always emitted in the
order of the table above.

## Example

```bash
SECURITY_CONTACT=mailto:security@example.com \
SECURITY_EXPIRES=2030-12-31T23:59:59Z \
uv run --package backend uvicorn backend.main:app
curl http://127.0.0.1:8000/.well-known/security.txt
```

```text
Contact: mailto:security@example.com
Expires: 2030-12-31T23:59:59Z
```

## Tests

- pytest: `tests/routes/test_security_txt.py` covers the generator with
  every field, required fields only and no field, and the HTTP route
  (status, media type, body).
- behave: `features/security_txt.feature` with the scenarios "Security.txt
  returns required fields", "Security.txt with all fields configured" and
  "Security.txt with no fields configured". The settings are patched in
  process.
