# OAuth2 and OpenID Connect authorization server

This feature turns the service into an OAuth2 / OpenID Connect provider:
client registration, the authorization endpoint with PKCE and a consent
screen, the token endpoint with its grants, revocation, introspection, the
userinfo endpoint and a CORS policy driven by the registered clients. It
builds on the signing keys (token signatures), the sessions and login (the
resource owner authenticates with the session cookie) and the tenancy
(issuer).

## What it does

### Clients

`OAuth2ClientService` creates and looks up the `oauth2_clients`. A confidential
client gets a generated secret that is stored as an Argon2id hash and shown
once; a public client has none. Each client has its redirect URIs, allowed
scopes (wildcards such as `resource:*` are supported), allowed grant types,
allowed CORS origins and the flags `require_pkce`, `require_consent` and
`is_active`. `validate_redirect_uri`, `validate_scopes` and
`validate_grant_type` apply those rules. The service also issues and consumes
the single-use authorization codes (stored hashed).

### Authorization endpoint

`GET /oauth2/authorize` validates the request (`response_type=code`, a
registered `redirect_uri`, allowed scopes, PKCE when the client requires it),
then:

- sends users without a valid session to `/auth/login?next=<authorization URL>`
  (also when `prompt=login`);
- shows the consent screen when the client requires consent, otherwise issues
  a code and redirects to `redirect_uri?code=...&state=...`;
- reports errors to the client by redirect (`error`, `error_description`,
  `state`) once the redirect URI is trusted, and as an HTML error page
  (status 400) when the client or the redirect URI is not.

`POST /oauth2/authorize` records the consent decision (`allow` issues the code,
`deny` redirects with `error=access_denied`). The endpoint also understands
`request_uri` (pushed authorization requests, RFC 9126) and a signed `request`
object (RFC 9101); the services behind them (`PARService`, `JARService`) are
part of this feature, the endpoint that pushes requests comes with the next
one.

### Token endpoint

`POST /oauth2/token` authenticates the client (HTTP Basic or form fields; a
public client sends only its `client_id`) and dispatches on `grant_type`:

- `authorization_code`: checks the code, the client, the redirect URI and the
  PKCE `code_verifier` (`S256`), consumes the code and returns an access
  token, a refresh token and, with the `openid` scope, an ID token;
- `refresh_token`: rotates the refresh token (the previous one is consumed);
- `client_credentials`: a machine token without user and without refresh token;
- `password`: legacy resource owner password grant, with the MFA code as `otp`;
- `urn:ietf:params:oauth:grant-type:device_code`: completes a device
  authorization (the device endpoints are in the next feature);
- `urn:ietf:params:oauth:grant-type:token-exchange` (RFC 8693): exchanges a
  subject token for a token with a narrower scope or another audience. A
  client's allowed scopes may contain `*`, a resource wildcard such as
  `users:*` or a group scope declared in the `SCOPE_GROUPS` setting; no
  group exists by default, so the groups of a deployment are not in the code.

Access tokens are RS256 JWTs signed with the active key (`kid` header) with the
claims `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, `scope` and `client_id`; their
metadata is stored in `access_tokens` so that they can be revoked. Refresh
tokens are opaque and stored hashed. The `sub` claim is a pairwise identifier
(`PairwiseSubjectService`): each tenant sees a different, opaque subject for
the same user. A grant the client was not given answers
`unauthorized_client`; bad client credentials answer `401 invalid_client`.
Errors have the form `{"detail": {"error": ..., "error_description": ...}}`.

### Revocation, introspection and userinfo

- `POST /oauth2/revoke` (RFC 7009) revokes an access or refresh token of the
  authenticated client.
- `POST /oauth2/introspect` (RFC 7662) reports whether a token is active and
  its metadata. The client needs the `introspect` scope; personal access
  tokens (`pat_` prefix) can be introspected too. Anything unknown, expired or
  revoked is simply `{"active": false}`.
- `GET` and `POST /userinfo` return the claims of the user for a bearer access
  token that has the `openid` scope: `sub` always, then `profile`, `email`,
  `phone` and `address` claims according to the scopes.
- `OAuth2CORSMiddleware` answers CORS preflights and adds the CORS headers on
  the token, revocation, introspection, userinfo, discovery and JWKS paths, but
  only for origins that an active client allows: its `allowed_origins`, or the
  origins of its redirect URIs when it declares none. A refused preflight
  answers 403.

## Endpoints

### `userinfo`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/userinfo` | `get_userinfo` | Return OIDC claims for the authenticated end-user (GET). |
| POST | `/userinfo` | `post_userinfo` | Return OIDC claims for the authenticated end-user (POST). |

### `oauth2.authorize`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/oauth2/authorize` | `authorize_get` | Initiate the OAuth2 authorization code flow. |
| POST | `/oauth2/authorize` | `authorize_post` | Submit the OAuth2 consent decision and obtain an authorization code. |

### `oauth2.token`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| POST | `/oauth2/token` | `token_endpoint` | Issue OAuth2 access tokens for all supported grant types. |

### `oauth2.revoke`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| POST | `/oauth2/revoke` | `revoke_token` | Revoke an OAuth2 access token or refresh token (RFC 7009). |

### `oauth2.introspect`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| POST | `/oauth2/introspect` | `introspect_token` | Validate a token and return its active state and metadata. |

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `AUTHORIZATION_CODE_EXPIRY_MINUTES` | `10` | Authorization code validity |
| `ACCESS_TOKEN_EXPIRY_MINUTES` | `60` | Access token validity (1 hour) |
| `REFRESH_TOKEN_EXPIRY_DAYS` | `30` | Refresh token validity (30 days) |
| `ID_TOKEN_EXPIRY_MINUTES` | `60` | ID token validity (1 hour) |
| `DEVICE_CODE_EXPIRY_MINUTES` | `15` | Device code validity |
| `DEVICE_CODE_INTERVAL` | `5` | Minimum polling interval in seconds |
| `PAR_REQUEST_EXPIRY_SECONDS` | `60` | PAR request_uri validity (1 minute) |
| `SCOPE_GROUPS` | `{}` | JSON object of group scopes for token exchange: `{"suite:*": ["notes", "tasks"]}` lets a client allowed `suite:*` be granted any scope of the resources `notes` and `tasks` |

## Data model

Uses `oauth2_clients`, `authorization_codes`, `access_tokens`,
`refresh_tokens`, `device_codes`, `par_requests` and `pairwise_subjects`. The
public client used by the Swagger UI of `/docs` is a row of `oauth2_clients` like
any other; its `client_id` is the `SWAGGER_CLIENT_ID` setting. No migration inserts it.

## Tests

- pytest: 24 new test modules and 1 existing modules extended.
  New modules: `tests/test_client_repository.py`, `tests/test_device_code_repository.py`, `tests/test_device_code_service.py`, `tests/test_jar_service.py`, `tests/test_middleware_cors.py`, `tests/test_oauth2_client_service.py`, `tests/test_pairwise_repository.py`, `tests/test_pairwise_service.py`, `tests/test_pairwise_token_integration.py`, `tests/test_par_repository.py`, `tests/test_par_service.py`, `tests/test_pat_repository.py`, `tests/test_pat_service.py`, `tests/test_pkce.py`, `tests/test_role_repository.py`, `tests/test_routes_oauth2_authorize.py`, `tests/test_routes_oauth2_introspect.py`, `tests/test_routes_oauth2_revoke.py`, `tests/test_routes_oauth2_token.py`, `tests/test_routes_userinfo.py`, `tests/test_schemas_oauth2.py`, `tests/test_token_exchange_service.py`, `tests/test_token_repository.py`, `tests/test_token_service.py`.
  Extended: `tests/test_api_deps.py`.
- behave: `features/oauth2_server.feature` with the scenarios *The authorization code flow with PKCE issues verifiable tokens*, *The userinfo endpoint returns the claims allowed by the scopes*, *A code cannot be exchanged twice*, *The PKCE verifier must match the challenge*, *Unauthenticated users are sent to the login page*, *PKCE is mandatory for the client*, *Scopes outside the client allowance are refused*, *Authorization requests with an untrusted client or redirect URI show an error page*, *A consent screen is shown to clients that require it*, *The client credentials grant issues a machine token*, *Client authentication is enforced*, *A grant type the client was not given is refused*, *Refresh tokens are rotated and can be revoked*, *Token introspection reports the state of a token*, *Browser applications may call the token endpoint from registered origins only*, *A group scope declared in the settings covers the scopes of its resources in a token exchange*.

The behave scenarios run complete flows through the application: the user signs
in, a PKCE authorization request is issued, the code is exchanged, the access
token is verified offline with the key read from the JWKS endpoint, then used
for userinfo, introspection, refresh and revocation.

### Browser scenarios

`features/browser/oauth2_server.feature` is tagged `@browser`: its 10 scenarios drive the
application in Chromium (see [browser tests](../../testing/index.md)).

- A visitor signs in and is sent back to the client with an authorization code
- A user who is already signed in is not asked to sign in again
- A client that requires consent shows the consent screen
- Denying the consent sends an access_denied error to the client
- The code granted on the consent screen can be redeemed once
- A client asking for a scope outside its allowance gets an error redirect
- PKCE is mandatory
- An untrusted client or redirect URI shows an error page and no redirect
- A browser application reads the keys and talks to the token endpoint from its registered origin
- A page of an unregistered application is blocked by the browser

A second live server plays the client application: its callback page prints the redirect it receives, and the code is redeemed over the test client. The scenarios also check what Chromium enforces for cross-origin calls to the token, keys and discovery endpoints.
