# Server and services status

Endpoints that report the state of the host and of the services around the
robot. They are protected by the `reachy:status:read` scope of the
[JWT authentication](03-jwt-auth.md).

## Endpoints

Mounted under `/api/status`, tag `status`.

| Endpoint | Scope | Response |
| --- | --- | --- |
| `GET /api/status/server` | `reachy:status:read` | `timestamp`, `hostname`, `platform`, `python_version` and `status` (`online`) of the host running the service |
| `GET /api/status/services` | `reachy:status:read` | `services`: a list of `{name, status, port}` |

The server status is computed from the `platform` module. The services list
is static placeholder data (three entries, all `running`): the original code
base marks the real service monitoring as a TODO, so nothing is probed.

Every call writes an `ACTION: get_server_status` or `get_services_status`
line with the user id in the logs. Authentication errors follow the JWT
feature (401, 403, 503).

## Settings

No setting of its own.

## Data model

None.

## How it is tested

Pytest (`test_api_status.py`): both handlers called directly (payload and
audit log line), the routes mounted under `/api`, and HTTP calls through
`TestClient` with the JWT validation faked (missing token, wrong scope,
right scope).

Behave (`apps/reachy-mini-api/features/status.feature`):

- Status requires authentication
- Status requires the status scope
- Get the server status
- Get the services status
