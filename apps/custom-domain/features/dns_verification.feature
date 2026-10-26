Feature: DNS verification
  A customer must point a CNAME record at the platform before a certificate can be issued.
  The DNS service checks that record and the Celery tasks drive the domain status from the
  result. Resolvers, the database and the task queue are replaced by in-process fakes.

  Scenario: A matching CNAME record is accepted
    Given the domain "shop.example.com" has a CNAME record pointing to "apps.example.com."
    When I check the CNAME of "shop.example.com" against "apps.example.com"
    Then the DNS check succeeds

  Scenario: A CNAME record pointing elsewhere is rejected
    Given the domain "shop.example.com" has a CNAME record pointing to "other.example.net."
    When I check the CNAME of "shop.example.com" against "apps.example.com"
    Then the DNS check fails with "CNAME points to other.example.net, expected apps.example.com"

  Scenario: A missing domain is reported
    Given the domain "shop.example.com" does not exist in DNS
    When I check the CNAME of "shop.example.com" against "apps.example.com"
    Then the DNS check fails with "Domain does not exist (NXDOMAIN)"

  Scenario: Successful verification triggers SSL provisioning
    Given a domain "shop.example.com" with the status "pending" in the database
    And the DNS check of the task succeeds
    When the DNS verification task runs for "shop.example.com"
    Then the domain "shop.example.com" has the status "dns_verified"
    And SSL provisioning was queued for "shop.example.com"

  Scenario: A failed verification is retried and counted
    Given a domain "shop.example.com" with the status "pending" in the database
    And the DNS check of the task fails with "No CNAME record found"
    When the DNS verification task runs for "shop.example.com"
    Then the task asks to be retried
    And the domain "shop.example.com" has the error "No CNAME record found"
    And the domain "shop.example.com" has 1 failed verification

  Scenario: Verification gives up when the retries are exhausted
    Given a domain "shop.example.com" with the status "pending" in the database
    And the DNS check of the task fails with "No CNAME record found"
    And the task may not be retried
    When the DNS verification task runs for "shop.example.com"
    Then the domain "shop.example.com" has the status "failed"
    And an "error" event with the code "DNS_VERIFICATION_FAILED" was published

  Scenario: The periodic check only queues domains that are due
    Given a domain "never-checked.example.com" with the status "pending" in the database
    And a domain "just-checked.example.com" with the status "pending" in the database
    And the domain "just-checked.example.com" was checked 1 minutes ago
    And a domain "live.example.com" with the status "active" in the database
    When the periodic pending domains check runs
    Then DNS verification was queued for "never-checked.example.com" only

  Scenario: The periodic check is scheduled
    Then the beat schedule runs "custom_domain.tasks.verification.check_pending_domains"

  Scenario: The periodic scan is published to the queue the worker consumes
    Then the beat entry "check-pending-domains" is published to the queue "custom-domain"
