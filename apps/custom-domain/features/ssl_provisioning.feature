Feature: SSL provisioning
  A domain whose DNS is verified gets an HTTP-only nginx configuration, a Let's Encrypt
  certificate and finally the full HTTPS configuration. The Celery task is executed
  in-process against an in-memory database, with nginx and certbot replaced by fakes.

  Scenario: A verified domain becomes active
    Given a domain "shop.example.com" with the status "dns_verified" in the database
    And certbot issues a certificate expiring in 90 days
    When the SSL provisioning task runs for "shop.example.com"
    Then the domain "shop.example.com" has the status "active"
    And the domain "shop.example.com" has an SSL expiry date
    And the nginx configuration was written 2 times and reloaded 2 times
    And the progress events are
      | event          | step       |
      | status_change  |            |
      | step_started   | nginx_http |
      | step_completed | nginx_http |
      | step_started   | certbot    |
      | step_completed | certbot    |
      | step_started   | nginx_https |
      | step_completed | nginx_https |
      | status_change  |            |
      | completed      |            |

  Scenario: A certificate failure marks the domain as failed
    Given a domain "shop.example.com" with the status "dns_verified" in the database
    And certbot fails with "ACME challenge failed. Verify DNS configuration."
    When the SSL provisioning task runs for "shop.example.com"
    Then the domain "shop.example.com" has the status "failed"
    And the domain "shop.example.com" has the error "ACME challenge failed. Verify DNS configuration."
    And an "error" event with the code "SSL_PROVISIONING_FAILED" was published

  Scenario: A Let's Encrypt rate limit schedules a retry
    Given a domain "shop.example.com" with the status "dns_verified" in the database
    And certbot fails with "Let's Encrypt rate limit exceeded. Try again later."
    When the SSL provisioning task runs for "shop.example.com"
    Then the task asks to be retried
    And the domain "shop.example.com" has the status "ssl_provisioning"

  Scenario: A deleted domain is ignored
    Given a domain "shop.example.com" with the status "dns_verified" in the database
    And the domain "shop.example.com" is soft-deleted
    When the SSL provisioning task runs for "shop.example.com"
    Then no nginx configuration was written

  Scenario: Deprovisioning removes the nginx configuration and the certificate
    Given a domain "shop.example.com" with the status "deprovisioning" in the database
    When the deprovisioning task runs for "shop.example.com"
    Then the nginx configuration of "shop.example.com" was removed
    And the certificate of "shop.example.com" was revoked
    And the domain "shop.example.com" is deleted
    And the domain "shop.example.com" has the status "deprovisioning"

  Scenario: A domain removed by maintenance is marked as deprovisioning first
    Given a domain "shop.example.com" with the status "active" in the database
    When the deprovisioning task runs for "shop.example.com"
    Then an "status_change" event with the status "deprovisioning" was published

  Scenario: Tasks are published to the queue the worker consumes
    Then the Celery default queue is "custom-domain"
    And the task "custom_domain.tasks.provisioning.provision_domain_ssl" is routed to the queue "custom-domain"
    And the task "custom_domain.tasks.provisioning.deprovision_domain" is routed to the queue "custom-domain"

  Scenario: Certbot requests a webroot certificate through the helper
    Given the system commands are recorded instead of executed
    And certbot is enabled with the e-mail "ops@example.com"
    When I request a certificate for "shop.example.com"
    Then the recorded commands are
      """
      sudo -n /opt/custom-domain/privileged-helper --certbot-bin /opt/certbot/bin/certbot --webroot /srv/acme --email ops@example.com certbot-issue shop.example.com
      sudo -n /opt/custom-domain/privileged-helper --openssl-bin /opt/openssl/bin/openssl --letsencrypt-dir /srv/letsencrypt cert-dates shop.example.com
      """

  Scenario: A missing e-mail is reported instead of guessed
    Given the system commands are recorded instead of executed
    And certbot is enabled without an e-mail
    When I request a certificate for "shop.example.com"
    Then the certificate request fails with "CERTBOT_EMAIL is not configured"
    And no system command was run

  Scenario: Certbot can be disabled
    Given the system commands are recorded instead of executed
    And certbot is disabled
    When I request a certificate for "shop.example.com"
    Then the certificate request succeeds
    And no system command was run
