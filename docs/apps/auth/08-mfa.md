# Multi-factor authentication

Users can protect their account with a time-based one-time password (TOTP)
from an authenticator app, with single-use backup codes, and with one-time
codes sent by e-mail. This feature adds the MFA service and repository and
the endpoints and pages to enrol, challenge and disable the factors. The
login feature that follows uses them to challenge users who enabled MFA.

## What it does

- `MFAService.setup_totp` generates a base32 TOTP secret, stores it
  encrypted with AES-256-GCM (the key is `JWKS_ENCRYPTION_KEY`) as a pending
  secret and returns the secret, the `otpauth://` URI and a QR code as a
  base64 PNG data URL. The issuer shown in the authenticator app is
  `MFA_ISSUER_NAME`.
- `enable_totp` activates TOTP once the user proves possession by sending a
  valid code, and creates 10 backup codes in the form `XXXX-XXXX`; only their
  SHA-256 hashes are stored, so they are shown once. Codes are accepted with
  a tolerance of one 30-second step on each side.
- `verify_mfa_code` accepts a 6 digit TOTP code or a backup code; a backup
  code is marked as used on first success.
- `regenerate_backup_codes` and `disable_totp` require a valid TOTP code, so
  that a stolen session cookie alone cannot weaken the account. Disabling
  TOTP deletes the secret and the backup codes.
- Email codes: `send_mfa_email_code` stores the hash of a 6 digit code valid
  for `MFA_EMAIL_CODE_EXPIRY_MINUTES`, and `verify_email_code` consumes it
  once. `verify_mfa_code_with_email` accepts TOTP, backup or e-mail codes.
  The e-mail is rendered from the `mfa_code` template and queued through the
  Celery e-mail task of the registration feature.
- The endpoints authenticate with the session cookie (`401` without it) and
  dispatch the `mfa.enabled`, `mfa.disabled`, `mfa.backup_codes.generated`,
  `mfa.challenge.success` and `mfa.challenge.failed` webhook events. The
  HTML pages (`/auth/mfa/setup`, `/auth/mfa/setup/reconfigure`,
  `/auth/mfa/email`) render the enrolment, backup code and e-mail challenge
  templates with the tenant branding. The enrolment page confirms the code
  with `fetch` because the endpoint takes JSON: the backup codes it returns
  replace the form, and a wrong code is shown in place.

## Endpoints

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/auth/mfa/status` | `get_mfa_status` | Return TOTP enablement state and backup code counts for the current user. |
| POST | `/auth/mfa/totp/setup` | `setup_totp` | Initialise TOTP enrolment for the current user. |
| POST | `/auth/mfa/totp/verify` | `verify_and_enable_totp` | Confirm the pending TOTP secret and activate TOTP for the current user. |
| POST | `/auth/mfa/totp/disable` | `disable_totp` | Deactivate TOTP for the current user after confirming the current code. |
| POST | `/auth/mfa/backup-codes/regenerate` | `regenerate_backup_codes` | Invalidate existing backup codes and issue a new set. |
| POST | `/auth/mfa/verify` | `verify_mfa_code` | Verify a TOTP code or a single-use backup code during an MFA challenge. |
| GET | `/auth/mfa/setup` | `mfa_setup_page` | Render the TOTP enrolment page with a QR code for authenticator apps. |
| POST | `/auth/mfa/setup/reconfigure` | `mfa_setup_reconfigure` | Replace the active TOTP secret with a newly generated one. |
| POST | `/auth/mfa/email/send` | `send_mfa_email` | Generate and email a time-limited OTP to the current user's primary address. |
| POST | `/auth/mfa/email/verify` | `verify_mfa_email` | Validate the email OTP submitted by the current user. |
| GET | `/auth/mfa/email` | `mfa_email_page` | Render the email OTP verification page for browser-based MFA flows. |

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `MFA_ISSUER_NAME` | `Auth` | Issuer name shown in authenticator apps |
| `MFA_EMAIL_CODE_EXPIRY_MINUTES` | `10` | MFA email code validity in minutes |

## Data model

Uses `user_mfas` (encrypted TOTP secret, enabled flag and date),
`mfa_backup_codes` (hash and `used_at`) and `mfa_email_codes` (e-mail, hash,
expiry and `used_at`).

## Tests

- pytest: 3 new test modules and 1 existing modules extended.
  New modules: `tests/test_mfa_repository.py`, `tests/test_mfa_service.py`, `tests/test_routes_auth_mfa.py`.
  Extended: `tests/test_api_deps.py`.
- behave: `features/mfa.feature` with the scenarios *MFA endpoints require a session*, *A user without MFA has no backup codes*, *Enrolling an authenticator app*, *A wrong code does not enable TOTP*, *A user who enabled TOTP cannot enrol twice*, *A TOTP code passes the challenge*, *A backup code can be used only once*, *Backup codes can be regenerated*, *Disabling TOTP needs a valid code*, *An e-mail code can be used as a second factor*.

The behave scenarios drive the HTTP endpoints with a real session and compute
the TOTP codes with `pyotp` from the secret returned by the enrolment, so the
whole enrol, challenge, regenerate and disable cycle runs against the real
service and the in-memory database. The e-mail code is read from the captured
message.

### Browser scenarios

`features/browser/mfa.feature` is tagged `@browser`: its 8 scenarios drive the
application in Chromium (see [browser tests](../../testing/index.md)).

- The setup page asks the visitor to sign in first
- The setup page shows the QR code and the secret of the authenticator app
- The authenticator app is enrolled with the code it displays
- A wrong code keeps the setup open until the right one is entered
- The setup page of a user who enrolled offers to start again
- The e-mail page asks to sign in first
- A code received by e-mail is entered on the e-mail verification page
- A wrong e-mail code is refused with a message

The scenarios read the secret displayed next to the QR code, compute the code with `pyotp`, enrol the authenticator app from the setup page, show the backup codes and confirm an e-mail code on the e-mail page.
