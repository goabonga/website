# Device authorization and pushed authorization requests

This feature adds the two OAuth2 extensions whose services were introduced
with the authorization server: the device authorization grant (RFC 8628) for
devices without a usable browser, and pushed authorization requests (RFC 9126)
for clients that want to send their authorization parameters over an
authenticated back channel.

## What it does

### Device authorization grant

1. The device calls `POST /oauth2/device` with its `client_id` (confidential
   clients authenticate with their secret) and the scopes it wants. The client
   must be allowed the `urn:ietf:params:oauth:grant-type:device_code` grant,
   otherwise the answer is `unauthorized_client`. The response carries a
   `device_code`, a short `user_code`, the `verification_uri`
   (`/oauth2/device/verify`), a `verification_uri_complete` that embeds the user
   code (for QR codes), `expires_in` (`DEVICE_CODE_EXPIRY_MINUTES`) and the
   polling `interval` (`DEVICE_CODE_INTERVAL`).
2. The user opens `GET /oauth2/device/verify` on another screen. Without a
   session they are sent to the login page. They type the user code
   (`POST /oauth2/device/verify`); an unknown, expired or already used code is
   reported on the page. Clients that do not require consent are authorized
   immediately, the others get the consent screen.
3. `POST /oauth2/device/complete` records the decision (`allow` or `deny`).
4. Meanwhile the device polls the token endpoint of the previous feature with
   `grant_type=urn:ietf:params:oauth:grant-type:device_code`. It receives
   `authorization_pending` until the user decides, `slow_down` when it polls
   faster than the interval, `expired_token` after the expiry, `access_denied`
   after a refusal and finally the tokens. The device code is consumed when the
   tokens are issued.

The device codes are stored hashed; the user code is the only value a human
types.

Known limitation of the code as migrated: the poll time used for `slow_down`
is written just before `authorization_pending` is returned, but an HTTP error
rolls the request transaction back, so it is not kept in that case.

### Pushed authorization requests

`POST /oauth2/par` takes the same parameters as an authorization request
(`response_type`, `redirect_uri`, `scope`, `state`, `code_challenge`,
`nonce`, ...) and authenticates the client. It validates them like the
authorization endpoint does (scopes, redirect URI, PKCE) and answers with a
`request_uri` of the form `urn:ietf:params:oauth:request_uri:<token>` and its
lifetime `expires_in` (`PAR_REQUEST_EXPIRY_SECONDS`). The client then sends the
browser to `GET /oauth2/authorize?client_id=...&request_uri=...`. A `request_uri`
is bound to the client that pushed it, can be used once and expires.

## Endpoints

### `oauth2.device`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| POST | `/oauth2/device` | `device_authorization` | Issue a device code and user code to begin the Device Authorization Grant. |
| GET | `/oauth2/device/verify` | `device_verify_form` | Render the user-facing device verification page (RFC 8628 §3.3). |
| POST | `/oauth2/device/verify` | `device_verify_code` | Validate a submitted user code and present the consent screen. |
| POST | `/oauth2/device/complete` | `device_complete` | Record the user's consent decision and finalize device authorization. |

### `oauth2.par`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| POST | `/oauth2/par` | `pushed_authorization_request` | Push an authorization request to the server and receive a request_uri. |

The PAR endpoint answers with status 200 although its docstring mentions 201.

## Settings

This feature adds no setting; it uses `DEVICE_CODE_EXPIRY_MINUTES`,
`DEVICE_CODE_INTERVAL` and `PAR_REQUEST_EXPIRY_SECONDS` from the authorization
server feature.

## Data model

Uses `device_codes` (hashed device code, user code, status, scopes, expiry,
polling interval and last poll time) and `par_requests`.

## Tests

- pytest: 2 new test modules.
  New modules: `tests/test_routes_oauth2_device.py`, `tests/test_routes_oauth2_par.py`.
- behave: `features/device_par.feature` with the scenarios *A device obtains tokens once the user approves it on another screen*, *A denied device never receives tokens*, *Polling faster than the interval is told to slow down*, *An expired device code is refused*, *The verification page requires a signed-in user*, *A wrong user code is rejected*, *A client that is not allowed the device grant cannot start the flow*, *A pushed authorization request is exchanged for a single-use reference*, *Pushing a request requires client authentication*, *A pushed request is validated like a direct one*.

The behave scenarios play both sides of each flow against the application: the
device and the browser of the user for the device grant, the client and the
browser for the pushed request.

### Browser scenarios

`features/browser/device_par.feature` is tagged `@browser`: its 6 scenarios drive the
application in Chromium (see [browser tests](../../testing/index.md)).

- A device is approved by scanning the verification link
- The code of the device can be typed on the verification page
- A wrong code is explained on the verification page
- Denying the device tells the user and the device never gets tokens
- A code that was already approved cannot be used again
- A pushed authorization request is redeemed once in the browser

The device talks to the live server over HTTP, the user opens the verification link in the browser, signs in on the way, and approves or denies on the consent page.
