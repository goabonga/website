Feature: Certificate records and database migrations
  As an operator
  I want every issued certificate to be recorded in PostgreSQL
  So that issuance can be audited and certificates revoked

  Scenario: Database URLs are converted to the asyncpg driver
    Given the database URL "postgresql://portal@db/vpn_portal"
    When the async database URL is computed
    Then the async database URL should be "postgresql+asyncpg://portal@db/vpn_portal"

  Scenario: Heroku-style database URLs are converted too
    Given the database URL "postgres://portal@db/vpn_portal"
    When the async database URL is computed
    Then the async database URL should be "postgresql+asyncpg://portal@db/vpn_portal"

  Scenario: A fresh certificate is valid
    Given a certificate valid for 10 more minutes
    Then the certificate should be valid

  Scenario: A revoked certificate is not valid
    Given a certificate valid for 10 more minutes
    And the certificate is revoked
    Then the certificate should be revoked
    And the certificate should not be valid

  Scenario: An expired certificate is not valid
    Given a certificate that expired 5 minutes ago
    Then the certificate should be expired
    And the certificate should not be valid

  Scenario: The migration creates the certificates table
    When the migrations are rendered as SQL for PostgreSQL
    Then the SQL should create the table "vpn_certificates"
    And the SQL should create the index "ix_vpn_certificates_serial_number"
    And the SQL should declare the serial number unique

  Scenario: The migrations have a single head
    Then the migration history should have exactly one head
