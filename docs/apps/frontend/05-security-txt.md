# security.txt

The server publishes the vulnerability disclosure policy described by
[RFC 9116](https://www.rfc-editor.org/rfc/rfc9116) so that security
researchers know whom to contact. The file is generated from settings; nothing
is stored on disk.

## Endpoint

| Method | Path | Description |
|--------|------|-------------|
| GET | `/.well-known/security.txt` | Plain text (`text/plain`), one `Field: value` line per configured field. Hidden from the OpenAPI schema. |

The route is registered before the [SPA catch-all](04-spa-serving.md), so it
is never answered with the application page. When no field is configured the
endpoint still answers `200` with an empty body.

## Settings

Fields are written in this order. A field whose setting is empty is omitted.
`Contact` and `Expires` are the fields required by the RFC; the application
does not enforce them, so keep them set in production.

| Variable | Field |
|----------|-------|
| `SECURITY_CONTACT` | `Contact` (for example a `mailto:` URI) |
| `SECURITY_EXPIRES` | `Expires` (ISO 8601 date-time) |
| `SECURITY_ENCRYPTION` | `Encryption` |
| `SECURITY_ACKNOWLEDGMENTS` | `Acknowledgments` |
| `SECURITY_PREFERRED_LANGUAGES` | `Preferred-Languages` |
| `SECURITY_CANONICAL` | `Canonical` |
| `SECURITY_POLICY` | `Policy` |
| `SECURITY_HIRING` | `Hiring` |
| `SECURITY_CSAF` | `CSAF` |

None of them is a secret. `Expires` has to be renewed before it passes, as the
RFC requires; the application does not warn about it.

## Code

`frontend.security_txt` exposes the ordered `FIELDS` table,
`generate_security_txt(settings)` and `create_router(settings)`. `create_app`
includes the router.

## Tests

pytest (`tests/test_security_txt.py`): defaults, empty content, required
fields, order of all fields, omission of empty ones, the plain-text response,
the empty response, the route not being captured by the catch-all and its
absence from the OpenAPI schema.

behave (`features/security_txt.feature`, steps in
`features/steps/security_txt_steps.py`):

- Configured fields are published as plain text
- Optional fields follow the required ones and empty fields are omitted
- Nothing is published when nothing is configured
- security.txt is not served by the application page

browser (`features/browser/security_txt.feature`, tag `@browser`, see [Browser
testing](../../testing/index.md)): the file is opened in Chromium.

- The contact is shown as plain text (status 200, `text/plain; charset=utf-8`,
  the configured fields on the page, no application page, no browser error)
- Nothing is published when nothing is configured
