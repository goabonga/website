# Login and password reset

This feature lets users sign in with their e-mail address and password,
challenges those who enabled MFA, opens the session and the cookies that the
previous features read, and lets users recover a forgotten password with a
single-use link.

## What it does

### Sign in

- `POST /auth/login/api` takes a JSON body with `email`, `password` and an
  optional `otp`. It authenticates with `AuthService`, then:
  - if the user enabled TOTP and sent no `otp`, it answers `403 MFA required`;
    an `otp` (TOTP, backup or e-mail code, see `verify_mfa_code_with_email`)
    that does not verify answers `403 Invalid verification code`;
  - when the request is attributed to a tenant, the tenant's trust policy
    decides whether the user may sign in (`403` otherwise);
  - it creates a session (`SessionService.create_session`) with the client IP
    address and user agent, dispatches the `login.success` and
    `session.created` webhook events and answers
    `{"message": "Login successful", "csrf_token": "..."}` with the session
    cookie (`HttpOnly`, `SameSite=Lax`, `Secure` unless `SESSION_COOKIE_SECURE`
    is off, `Max-Age` of `SESSION_EXPIRY_DAYS`). Wrong credentials answer
    `401 Invalid email or password` and dispatch `login.failed`.
- `GET /auth/login` renders the branded login page. `POST /auth/login` is the
  two-step browser flow: step 1 checks the password; if MFA is enabled it sets
  a short-lived (300 seconds) `mfa_login_challenge` cookie signed with
  HMAC-SHA256 and re-renders the form asking for the code, without creating a
  session. Step 2 (a POST with `otp`, or `send_email_code=1` to receive the
  code by e-mail) verifies the code against that challenge and then opens the
  session and redirects (303) to the `next` URL, or to `/auth/settings` (served by
  the settings pages feature, the last one) when there is none. A path starting
  with a single `/` is accepted; a protocol-relative one (`//host`), a value
  with a backslash, a tab or a line break, and an absolute URL that does not
  point to the current host are ignored, which prevents an open redirect. Wrong credentials re-render the form with `401`, a trust
  policy denial with `403`.

### Password reset

- `PasswordService.create_reset_token` stores the hash of a random token for
  an existing user, valid for `PASSWORD_RESET_EXPIRY_HOURS`. The forgot
  password endpoints e-mail a link to `/auth/reset-password?token=...`
  (built from `ISSUER`, or from the `reset_base_url` of a client application
  that proxies the flow) rendered from the `password_reset` template.
  They always answer `200` with the same message, so they cannot be used to
  enumerate accounts.
- `reset_password` consumes the token once, marks the previous passwords as
  not current and stores the new Argon2id hash. The JSON API requires at
  least 8 characters with an upper-case letter, a lower-case letter and a
  digit (`422` otherwise); an invalid, expired or reused token answers `400`.
  The matching webhook events are `user.password_reset_requested` and
  `user.password_reset_completed`.

## Endpoints

### `auth.password`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/auth/forgot-password` | `forgot_password_form` | Render the forgot-password HTML form. |
| POST | `/auth/forgot-password` | `forgot_password_submit` | Submit the forgot-password form and dispatch a reset email. |
| POST | `/auth/forgot-password/api` | `forgot_password_api` | Request a password reset link via JSON API. |
| GET | `/auth/reset-password` | `reset_password_form` | Render the reset-password HTML form authenticated by a URL token. |
| POST | `/auth/reset-password` | `reset_password_submit` | Submit the reset-password form and update the user credential. |
| POST | `/auth/reset-password/api` | `reset_password_api` | Reset a user password via JSON API using a single-use token. |

### `auth.login`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/auth/login` | `login_form` | Render the HTML login form for password-based authentication. |
| POST | `/auth/login` | `login_submit` | Process the HTML login form submission and establish a session cookie. |
| POST | `/auth/login/api` | `login_api` | Authenticate via JSON and establish a session cookie (API variant). |

## Settings

This feature adds no setting.

The cookie, session and password reset settings used here were introduced by
the previous features.

## Data model

Uses `sessions` (created at sign in) and `password_reset_tokens` (token
hash, expiry, `used_at`), plus the user, MFA and tenant trust tables read
during sign in.

## Tests

- pytest: 2 new test modules.
  New modules: `tests/test_routes_auth_login.py`, `tests/test_routes_auth_password.py`.
- behave: `features/login.feature` with the scenarios *The login form is served*, *Signing in through the API opens a session*, *Wrong credentials are refused*, *The session of a sign-in can be used to sign out*, *Signing in through the form redirects to the requested page*, *The login form reports wrong credentials*, *A user with TOTP must provide a code through the API*, *The login form asks for the code in a second step*, *A lost password is recovered with a single-use link*, *Asking for a reset does not reveal which addresses exist*, *A weak new password is refused*.

The behave scenarios sign in through the API and the HTML form with the
real services on the in-memory database. TOTP codes are computed with
`pyotp`, the reset token is read from the captured e-mail, and the
`Secure` flag of the cookies is switched off because the test client talks
plain HTTP.

### Browser scenarios

`features/browser/login.feature` is tagged `@browser`: its 13 scenarios drive the
application in Chromium (see [browser tests](../../testing/index.md)).

- The login page offers the form, the recovery and the registration links
- Signing in opens a session and goes to the requested page
- Wrong credentials are refused on the login page
- A user who is already signed in is sent on without seeing the form
- Only a page of the application can be the destination of a sign-in
- The second factor is asked in a second step
- A backup code answers the second factor once
- The second factor can be received by e-mail
- A lost password is recovered with a single-use link
- The old password stops working after a reset
- A reset form refuses a wrong confirmation or a weak password
- Asking for a reset does not reveal which addresses exist
- A reset link with an unknown token is refused

The scenarios sign in on the login page, answer the second factor with a TOTP code, a backup code or a code received by e-mail, try to leave the application through `next`, and recover a password with the link of the captured e-mail.
