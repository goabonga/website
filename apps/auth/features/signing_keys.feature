Feature: Signing keys
    As a relying party
    I want to fetch the public keys that sign the tokens of the server
    So that I can verify tokens offline, including across key rotations

    Background:
        Given a signing key store protected by a fresh encryption key

    Scenario: A generated key is published as a public JWK
        When the operator generates and activates a signing key
        And I send a GET request to "/.well-known/jwks.json"
        Then the response status is 200
        And the JWKS document lists 1 key
        And the published key is an RS256 signature key
        And the published keys expose no private material

    Scenario: A key that is not active yet is still published
        When the operator generates a signing key without activating it
        And I send a GET request to "/.well-known/jwks.json"
        Then the JWKS document lists 1 key
        And no key is active

    Scenario: Revoked keys are not published
        Given the operator generated and activated a signing key
        And the operator rotates the keys
        When the operator revokes the first key
        And I send a GET request to "/.well-known/jwks.json"
        Then the JWKS document lists 1 key
        And the published key is the active key

    Scenario: Rotation activates a new key and keeps the old one published
        Given the operator generated and activated a signing key
        When the operator rotates the keys
        And I send a GET request to "/.well-known/jwks.json"
        Then the JWKS document lists 2 keys
        And exactly one key is active

    Scenario: Private keys are encrypted at rest
        When the operator generates and activates a signing key
        Then the stored private key is not a PEM document
        And the stored private key can be decrypted with the encryption key
        And the stored private key cannot be decrypted with another key

    Scenario: Passwords are hashed with Argon2id
        When the password "correct horse battery staple" is hashed
        Then the hash starts with "$argon2id$"
        And the password "correct horse battery staple" matches the hash
        And the password "wrong password" does not match the hash
