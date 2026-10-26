# security.txt

The service publishes a `security.txt` file at the well-known location defined
by [RFC 9116](https://www.rfc-editor.org/rfc/rfc9116), so that security
researchers can find how to report a vulnerability.

## Endpoint

| Endpoint | Method | Description |
| --- | --- | --- |
| `/.well-known/security.txt` | GET | `text/plain` file generated from the settings |

The file is built on every request by
`analytics.routes.security_txt.generate_security_txt`. A field is written only
when its setting is not empty, one `Name: value` line per field, in this
order. With no setting at all the response is an empty `200` body. The
endpoint is not part of the OpenAPI schema.

## Settings

| Variable | Field written | Default |
| --- | --- | --- |
| `SECURITY_CONTACT` | `Contact` | empty |
| `SECURITY_EXPIRES` | `Expires` (ISO 8601) | empty |
| `SECURITY_ENCRYPTION` | `Encryption` | empty |
| `SECURITY_ACKNOWLEDGMENTS` | `Acknowledgments` | empty |
| `SECURITY_PREFERRED_LANGUAGES` | `Preferred-Languages` | empty |
| `SECURITY_CANONICAL` | `Canonical` | empty |
| `SECURITY_POLICY` | `Policy` | empty |
| `SECURITY_HIRING` | `Hiring` | empty |
| `SECURITY_CSAF` | `CSAF` | empty |

RFC 9116 requires `Contact` and `Expires`; the service does not enforce it, so
set both in every deployment.

Example `.env` fragment (also in `.env.example`):

```bash
SECURITY_CONTACT=mailto:security@example.com
SECURITY_EXPIRES=2026-12-31T23:59:59Z
SECURITY_PREFERRED_LANGUAGES=en
```

## Tests

pytest:

- `test_routes_security_txt.py`: empty output, a single field, all nine fields
  and the `text/plain` response.
- `test_config.py`: the `security_*` defaults and environment overrides.
- `test_main.py`: the route is registered.

behave (`features/security_txt.feature`):

- Empty security.txt when nothing is configured
- Configured fields are published
- Optional fields use their RFC 9116 names

The scenarios change the settings object in process and restore it after each
scenario.
