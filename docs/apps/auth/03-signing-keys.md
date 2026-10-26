# Signing keys

The service signs its tokens with RSA keys stored in the database. This
feature adds the key store (private keys encrypted at rest), the service
that generates, activates, rotates and revokes the keys, and the public
JWKS endpoint that relying parties use to verify signatures.

## What it does

- `auth.core.security` provides `AESEncryption` (AES-256-GCM with a random
  96-bit nonce prepended to the ciphertext) and the Argon2id password
  helpers (`hash_password`, `verify_password`, `check_needs_rehash`). The
  password helpers are used by the account features that follow.
- `auth.core.encryption` exposes `encrypt_value` and `decrypt_value`, which
  encrypt arbitrary strings with the key from `JWKS_ENCRYPTION_KEY`. Without
  that variable they raise `ValueError`.
- `auth.db.repositories.jwk.JWKRepository` holds the SQL for the `jwks`
  table. Repositories never commit; the service owns the transaction.
- `auth.services.jwks.JWKSService` generates 2048-bit (configurable) RSA
  key pairs, stores the PEM private key encrypted and the public key in
  clear, and offers:
  - `generate_key(activate=...)`: create a key; activating it deactivates
    the other active key.
  - `activate_key(kid)`: make one key the signing key (a revoked key cannot
    be activated).
  - `revoke_key(kid)`: deactivate the key and set `revoked_at`.
  - `rotate_keys()`: generate and activate a new key. The previous key
    stays published until it is revoked, so tokens signed with it remain
    verifiable.
  - `delete(kid)`: delete a key, only once it has been revoked.
  - `to_jwk_public(key)`: the RFC 7517 representation (`kty`, `kid`, `use`,
    `alg`, `n`, `e`) served to clients.
- `GET /.well-known/jwks.json` returns every non-revoked key; private key
  material is never part of the response.

`auth.api.deps` gains `get_encryption` and `get_jwks_service`, the
dependencies other features use to sign and verify tokens.

## Endpoints

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/.well-known/jwks.json` | `jwks` | Return the authorization server's public JSON Web Key Set. |

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `JWKS_ENCRYPTION_KEY` | (empty) | Base64-encoded 32-byte AES-256-GCM key that encrypts the private signing keys (also read from the systemd credential of the same name) |
| `JWKS_KEY_SIZE` | `2048` | RSA key size in bits for new keys; not read by the service yet, which takes the size as an argument (default 2048) |
| `JWKS_ROTATION_DAYS` | `90` | Intended rotation period in days; no job reads it yet |
| `JWKS_GRACE_PERIOD_DAYS` | `30` | Intended number of days a superseded key stays published; no job reads it yet |

`JWKS_ENCRYPTION_KEY` is a secret. Generate one with:

```bash
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

The setting can also be supplied as a systemd credential named
`JWKS_ENCRYPTION_KEY`; the credential wins over the environment variable.
Losing the key makes the stored private keys unreadable.

## Data model

Uses the `jwks` table created by the data model feature: `kid` (unique),
`kty`, `alg`, `use`, `private_key_encrypted`, `public_key_pem`, `is_active`
and `revoked_at`.

## Tests

- pytest: 5 new test modules and 2 existing modules extended.
  New modules: `tests/test_encryption.py`, `tests/test_jwk_repository.py`, `tests/test_jwks_service.py`, `tests/test_routes_jwks.py`, `tests/test_security.py`.
  Extended: `tests/test_api_deps.py`, `tests/test_routes_health.py`.
- behave: `features/signing_keys.feature` with the scenarios *A generated key is published as a public JWK*, *A key that is not active yet is still published*, *Revoked keys are not published*, *Rotation activates a new key and keeps the old one published*, *Private keys are encrypted at rest*, *Passwords are hashed with Argon2id*.

The behave scenarios run the real repository and service against an
in-memory SQLite database (see the data model feature) with a freshly
generated encryption key, so keys are really generated, encrypted, stored and
published through the HTTP endpoint.
