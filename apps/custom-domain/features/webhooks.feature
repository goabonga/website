Feature: Client status webhooks
  A client can register a callback URL and a shared secret. Status changes, completions and
  errors of its domains are then POSTed to it as signed JSON, so the application does not
  have to poll. Deliveries run in the Celery worker; the scenarios run them in-process with
  the HTTP call recorded.

  Scenario: An administrator configures the webhook of a client
    Given I am authenticated as client "ops" with scopes "custom-domain:admin custom-domain:admin:clients"
    When I send a POST request to "/api/v1/admin/clients" with JSON
      """
      {"client_id": "tenant-a", "name": "A", "default_upstream_target": "/run/a.sock",
       "default_cname_target": "apps.example.com",
       "webhook_url": "https://app.example.com/hooks",
       "webhook_secret": "0123456789abcdef0123456789abcdef"}
      """
    Then the response status is 201
    And the JSON field "webhook_url" equals "https://app.example.com/hooks"
    And the JSON field "has_webhook_secret" is true
    And the response does not contain "0123456789abcdef"

  Scenario: A webhook URL needs a secret
    Given I am authenticated as client "ops" with scopes "custom-domain:admin custom-domain:admin:clients"
    When I send a POST request to "/api/v1/admin/clients" with JSON
      """
      {"client_id": "tenant-a", "name": "A", "default_upstream_target": "/run/a.sock",
       "default_cname_target": "apps.example.com", "webhook_url": "https://app.example.com/hooks"}
      """
    Then the response status is 400

  Scenario: A plain http URL is refused
    Given I am authenticated as client "ops" with scopes "custom-domain:admin custom-domain:admin:clients"
    When I send a POST request to "/api/v1/admin/clients" with JSON
      """
      {"client_id": "tenant-a", "name": "A", "default_upstream_target": "/run/a.sock",
       "default_cname_target": "apps.example.com", "webhook_url": "http://app.example.com/hooks",
       "webhook_secret": "0123456789abcdef0123456789abcdef"}
      """
    Then the response status is 422

  Scenario: A provisioned domain notifies its client
    Given an authorized client "tenant-a" with a webhook
    And a domain "shop.example.com" with the status "dns_verified" in the database
    And webhook deliveries are recorded
    And certbot issues a certificate expiring in 90 days
    When the SSL provisioning task publishes its real events for "shop.example.com"
    And the queued webhooks are delivered
    Then the client received the events "domain.status_changed, domain.status_changed, domain.active"
    And every delivery is correctly signed
    And the last delivery describes the domain "shop.example.com" as "active"

  Scenario: A deleted domain notifies its client
    Given an authorized client "tenant-a" with a webhook
    And a domain "shop.example.com" with the status "deprovisioning" in the database
    And webhook deliveries are recorded
    When the deprovisioning task publishes its real events for "shop.example.com"
    And the queued webhooks are delivered
    Then the client received the events "domain.deleted"

  Scenario: A failed provisioning notifies its client
    Given an authorized client "tenant-a" with a webhook
    And a domain "shop.example.com" with the status "dns_verified" in the database
    And webhook deliveries are recorded
    And certbot fails with "ACME challenge failed. Verify DNS configuration."
    When the SSL provisioning task publishes its real events for "shop.example.com"
    And the queued webhooks are delivered
    Then the client received the events "domain.status_changed, domain.failed"
    And the last delivery describes the domain "shop.example.com" as "failed"

  Scenario: A client without a webhook receives nothing
    Given an authorized client "tenant-a" exists
    And a domain "shop.example.com" with the status "dns_verified" in the database
    And webhook deliveries are recorded
    And certbot issues a certificate expiring in 90 days
    When the SSL provisioning task publishes its real events for "shop.example.com"
    And the queued webhooks are delivered
    Then the client received no webhook

  Scenario: A deactivated client receives nothing
    Given an authorized client "tenant-a" with a webhook
    And the client "tenant-a" is deactivated
    And a domain "shop.example.com" with the status "dns_verified" in the database
    And webhook deliveries are recorded
    And certbot issues a certificate expiring in 90 days
    When the SSL provisioning task publishes its real events for "shop.example.com"
    And the queued webhooks are delivered
    Then the client received no webhook

  Scenario: A receiver that fails gets the delivery again
    Given an authorized client "tenant-a" with a webhook
    And a domain "shop.example.com" with the status "active" in the database
    And the receiver answers with the status 503
    When a webhook is delivered for "shop.example.com"
    Then the delivery is retried later

  Scenario: The SDK verifies a delivery and rejects a tampered one
    Given an authorized client "tenant-a" with a webhook
    And a domain "shop.example.com" with the status "active" in the database
    And the receiver answers with the status 200
    When a webhook is delivered for "shop.example.com"
    Then the SDK reads the event "domain.active" from the delivery
    And the SDK refuses the delivery when its body is altered
    And the SDK refuses the delivery when it is signed with another secret
