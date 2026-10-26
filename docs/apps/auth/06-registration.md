# Registration and email verification

Visitors create an account with an e-mail address and a password, then prove
that they own the address with a one-time code. This feature adds the user
repositories and services, password hashing at rest, e-mail delivery through
Celery (SMTP or the mailler service), the MJML e-mail templates, avatar
uploads and the registration and verification endpoints.

## What it does

### Accounts

- `UserService.create_user` creates, in one transaction, the `users` row, the
  primary `user_emails` row (lower-cased, unverified), the current
  `user_passwords` row (Argon2id hash, never the plain password) and an
  optional `user_profiles` row built from the OpenID Connect profile claims
  (name parts, nickname, preferred username, picture, website, gender,
  birthdate, locale, time zone, address and phone number). It records how
  the user registered (`registration_source`, client id, tenant, IP address
  and user agent). When the request is attributed to a tenant, the user is
  enrolled as a member with the tenant's default role and a `member.added`
  webhook event is dispatched. A duplicate address raises `ValueError`
  (`Email already registered`).
- `ProfileService` reads and updates profiles and converts them to claim
  dictionaries.
- `PasswordService` creates and consumes password reset tokens and changes
  passwords; the reset endpoints are part of the login feature.

### E-mail verification

- `EmailService.create_verification_code` stores the SHA-256 hash of a random
  6 digit code with an expiry (`VERIFICATION_CODE_EXPIRY_HOURS`).
  `verify_code` consumes a valid code once and marks the address verified.
- `send_verification_email` renders the `email_verification` template and
  queues the message with the `send_email` Celery task
  (`auth.tasks.email.send_email`), which delivers it either through SMTP
  (`EMAIL_BACKEND=smtp`) or through the mailler service
  (`EMAIL_BACKEND=mailler`, over HTTP or a Unix socket, authenticating with
  an OAuth2 client). Without `SMTP_HOST` the message is only logged.
- `EmailRenderer` compiles the MJML sources in `templates/emails/mjml` with
  `mrml`, injects the tenant branding, renders the Jinja2 variables and
  derives a plain text version (`templates/emails/txt`). A tenant can
  override the templates.

### Uploads

`UploadService.save_avatar` accepts images of the allowed types up to the
configured size and stores them under `{UPLOAD_DIRECTORY}/avatars/` with a
content-hash file name. `auth.main` serves the directory at `/uploads`.

### Endpoints

The JSON endpoints are meant for single page and mobile clients, the HTML
ones render the branded pages. `POST /auth/register` re-renders the form
with an error (400) on a duplicate address, a password mismatch or an
invalid avatar, and redirects (303) to `/auth/verify-email` on success. The
password policy of the JSON API requires 8 to 128 characters with a
lower-case letter, an upper-case letter, a digit and a special character.
`/auth/resend-verification` always answers 200 so that it cannot be used to
find out which addresses are registered.

### `auth.register`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/auth/register` | `register_form` | Render the self-registration HTML form. |
| POST | `/auth/register` | `register_submit` | Process the self-registration form and create a new user account. |
| POST | `/auth/register/api` | `register_api` | Register a new user account via the JSON API. |

### `auth.verify`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/auth/verify-email` | `verify_email_form` | Render the email verification code entry page. |
| POST | `/auth/verify-email` | `verify_email_submit` | Submit the email verification code via the HTML form. |
| POST | `/auth/verify-email/api` | `verify_email_api` | Verify an email address using a one-time code (JSON API). |
| POST | `/auth/resend-verification` | `resend_verification_submit` | Re-send the email verification code via the HTML form. |
| POST | `/auth/resend-verification/api` | `resend_verification_api` | Re-send the email verification code (JSON API). |

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `EMAIL_BACKEND` | `smtp` | "smtp" or "mailler" |
| `SMTP_HOST` | (empty) | SMTP server hostname (empty = log to console) |
| `SMTP_PORT` | `587` | SMTP server port |
| `SMTP_TLS` | `True` | Use TLS |
| `SMTP_USER` | (empty) | SMTP username |
| `SMTP_PASSWORD` | (empty) | SMTP password |
| `SMTP_FROM` | `noreply@example.com` | From email address |
| `MAILLER_URL` | (empty) | Mailler service URL (e.g., https://mailler.internal or http://localhost for UDS)     ) |
| `MAILLER_UNIX_SOCKET` | (empty) | Unix socket path (e.g., /run/mailler/mailler.sock) |
| `MAILLER_PROVIDER` | `brevo` | Default email provider (brevo, sendgrid, ses, protonmail) |
| `MAILLER_CLIENT_ID` | (empty) | OAuth2 client ID for mailler authentication |
| `MAILLER_CLIENT_SECRET` | (empty) | OAuth2 client secret for mailler authentication |
| `MAILLER_AUTH_URL` | (empty) | Auth service URL for token endpoint (e.g., https://auth.example.com)     ) |
| `VERIFICATION_CODE_EXPIRY_HOURS` | `24` | Verification code validity |
| `PASSWORD_RESET_EXPIRY_HOURS` | `1` | Password reset token validity |
| `TEMPLATES_PATH` | `/tmp/claude-1000/-home-anonymous-projects/569622e7-40b8-40f5-9751-10f9f1d12793/scratchpad/auth/asm/5/apps/auth/src/auth/templates` | Templates directory |
| `UPLOAD_DIRECTORY` | `uploads` | Directory for uploaded files |
| `UPLOAD_MAX_SIZE_MB` | `5` | Maximum file size in MB |
| `UPLOAD_ALLOWED_TYPES` | `image/jpeg,image/png,image/gif,image/webp` | Allowed MIME types |

`SMTP_PASSWORD` and `MAILLER_CLIENT_SECRET` are secrets; like
`JWKS_ENCRYPTION_KEY` they can also be provided as systemd credentials of the
same name.

## Background tasks

| Task | Beat schedule |
| --- | --- |
| `send_email` | on demand |

`docker compose -f apps/auth/compose.yml up -d` also starts a MailCatcher
(web UI on port 1080, SMTP on port 1025) for manual runs with
`EMAIL_BACKEND=smtp`, `SMTP_HOST=localhost`, `SMTP_PORT=1025` and
`SMTP_TLS=false`.

## Data model

Uses `users`, `user_emails`, `user_passwords`, `user_profiles` and
`verification_codes`, plus `tenant_members` for tenant registrations.

## Tests

- pytest: 15 new test modules and 1 existing modules extended.
  New modules: `tests/test_email_renderer_service.py`, `tests/test_email_service.py`, `tests/test_email_verification_repository.py`, `tests/test_mailler_service.py`, `tests/test_password_reset_repository.py`, `tests/test_password_service.py`, `tests/test_profile_repository.py`, `tests/test_profile_service.py`, `tests/test_routes_auth_register.py`, `tests/test_routes_auth_verify.py`, `tests/test_schemas_auth.py`, `tests/test_tasks_email.py`, `tests/test_upload_service.py`, `tests/test_user_repository.py`, `tests/test_user_service.py`.
  Extended: `tests/test_api_deps.py`.
- behave: `features/registration.feature` with the scenarios *A visitor registers through the JSON API*, *Weak passwords are refused*, *An address can only be registered once*, *The code received by e-mail verifies the address*, *A wrong code does not verify the address*, *A code can only be used once*, *A new code can be requested without revealing which addresses exist*, *The registration form is served and submitted*, *The registration form checks the password confirmation*, *Verification e-mails are rendered from the branded templates*, *Avatars must be small images*.

The behave scenarios drive the real routes, services and repositories against
the in-memory SQLite database and capture the messages handed to the Celery
e-mail task, so the verification codes are read from the e-mails exactly as
a user would.

### Browser scenarios

`features/browser/registration.feature` is tagged `@browser`: its 8 scenarios drive the
application in Chromium (see [browser tests](../../testing/index.md)).

- The registration page offers the form and a link to sign in
- The password requirements react while the visitor types
- A visitor registers and confirms the address with the e-mailed code
- The link of the verification e-mail leads to the verification page
- A wrong code is refused and a new one can be requested
- An address that is already registered is refused
- The browser stops a weak password or a wrong confirmation before sending it
- A visitor registers with a profile picture

The scenarios fill the registration form, type a weak password, upload an avatar and follow the verification link or type the code of the e-mail captured from the Celery e-mail task.
