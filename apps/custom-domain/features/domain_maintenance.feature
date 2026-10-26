Feature: Domain maintenance
  Periodic Celery tasks renew expiring certificates, retire domains whose DNS broke or that
  never became active, and purge old soft-deleted rows. The tasks run in-process against an
  in-memory database; DNS, certbot and the task queue are faked.

  Background:
    Given the maintenance tasks use the fake database and record the task queue

  Scenario: A certificate close to its expiry is renewed
    Given a domain "soon.example.com" with the status "active" in the database
    And the certificate of "soon.example.com" expires in 10 days
    And certbot reports 10 days left
    When the certificate expiry check runs
    Then SSL provisioning was requested for "soon.example.com"

  Scenario: A healthy certificate is left alone
    Given a domain "fine.example.com" with the status "active" in the database
    And the certificate of "fine.example.com" expires in 60 days
    When the certificate expiry check runs
    Then no SSL provisioning was requested

  Scenario: An active domain with valid DNS stays active
    Given a domain "shop.example.com" with the status "active" in the database
    And DNS answers correctly
    When the domain health check runs
    Then the domain "shop.example.com" has the status "active"

  Scenario: An active domain whose DNS broke is soft-deleted and deprovisioned
    Given a domain "shop.example.com" with the status "active" in the database
    And DNS fails with "No CNAME record found"
    When the domain health check runs
    Then the domain "shop.example.com" is soft-deleted
    And the domain "shop.example.com" was queued for deprovisioning without revoking its certificate

  Scenario: A domain that never became active is retired
    Given a domain "stale.example.com" with the status "pending" in the database
    And the domain "stale.example.com" was created 3 days ago
    And a domain "recent.example.com" with the status "pending" in the database
    And a domain "live.example.com" with the status "active" in the database
    And the domain "live.example.com" was created 3 days ago
    When the stale domain cleanup runs
    Then the domain "stale.example.com" is soft-deleted
    And the domain "recent.example.com" is not soft-deleted
    And the domain "live.example.com" is not soft-deleted

  Scenario: Old soft-deleted domains are purged
    Given a domain "old.example.com" with the status "failed" in the database
    And the domain "old.example.com" was soft-deleted 40 days ago
    And a domain "new.example.com" with the status "failed" in the database
    And the domain "new.example.com" was soft-deleted 5 days ago
    When the purge of deleted domains runs
    Then the domain "old.example.com" no longer exists
    And the domain "new.example.com" still exists

  Scenario: The maintenance tasks are scheduled
    Then the beat schedule runs "custom_domain.tasks.maintenance.check_certificate_expiry"
    And the beat schedule runs "custom_domain.tasks.maintenance.check_domain_health"
    And the beat schedule runs "custom_domain.tasks.maintenance.cleanup_stale_domains"
    And the beat schedule runs "custom_domain.tasks.maintenance.purge_deleted_domains"

  Scenario: The maintenance tasks are published to the worker queue at the configured times
    Then the beat entry "check-certificate-expiry" is published to the queue "custom-domain"
    And the beat entry "check-domain-health" is published to the queue "custom-domain"
    And the beat entry "cleanup-stale-domains" is published to the queue "custom-domain"
    And the beat entry "purge-deleted-domains" is published to the queue "custom-domain"
    And the beat entry "purge-deleted-domains" runs at hour 5 on day of week 0
