Feature: Data model and migrations
  Domains, authorized clients and nginx templates are stored in PostgreSQL.
  The scenarios render the alembic migration as SQL and exercise the models
  on an in-memory database.

  Scenario: The initial migration creates every table
    When I render the SQL of the alembic upgrade to head
    Then the SQL creates the table "custom_domains"
    And the SQL creates the table "authorized_clients"
    And the SQL creates the table "nginx_templates"

  Scenario: The migration can be reverted
    When I render the SQL of the alembic downgrade to base
    Then the SQL drops the table "custom_domains"
    And the SQL drops the table "authorized_clients"
    And the SQL drops the table "nginx_templates"

  Scenario: A new domain starts pending with no retries
    Given a stored domain "shop.example.com" owned by client "tenant-a"
    Then the stored domain "shop.example.com" has the status "pending"
    And the stored domain "shop.example.com" has 0 retries

  Scenario: A soft-deleted domain name can be registered again
    Given a stored domain "shop.example.com" owned by client "tenant-a"
    And the domain "shop.example.com" is soft-deleted
    When I register the domain "shop.example.com" again for client "tenant-b"
    Then the registration succeeds

  Scenario: Two live domains cannot share a name
    Given a stored domain "shop.example.com" owned by client "tenant-a"
    When I register the domain "shop.example.com" again for client "tenant-b"
    Then the registration is rejected as a duplicate
