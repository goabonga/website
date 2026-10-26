Feature: Brevo Webhooks
  Receive and process webhook events from Brevo email provider.

  # Webhooks require mailler:webhooks scope (machine-to-machine auth from gateway).

  Scenario: Receive delivered event
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "delivered",
        "email": "recipient@example.com",
        "X-Mailin-custom": ""
      }
      """
    Then the response status should be 200

  Scenario: Receive hard bounce event
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "hard_bounce",
        "email": "bounced@example.com",
        "reason": "User unknown",
        "X-Mailin-custom": ""
      }
      """
    Then the response status should be 200

  Scenario: Receive soft bounce event
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "soft_bounce",
        "email": "softbounce@example.com",
        "reason": "Mailbox full",
        "X-Mailin-custom": ""
      }
      """
    Then the response status should be 200

  Scenario: Receive permanent soft bounce (domain issue)
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "soft_bounce",
        "email": "invalid-domain@example.com",
        "reason": "Domain not found",
        "X-Mailin-custom": ""
      }
      """
    Then the response status should be 200

  Scenario: Receive blocked event
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "blocked",
        "email": "blocked@example.com",
        "reason": "Blocked by recipient",
        "X-Mailin-custom": ""
      }
      """
    Then the response status should be 200

  Scenario: Receive invalid event
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "invalid",
        "email": "invalid@example.com",
        "reason": "Invalid address",
        "X-Mailin-custom": ""
      }
      """
    Then the response status should be 200

  Scenario: Receive complaint event
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "complaint",
        "email": "complainer@example.com",
        "X-Mailin-custom": ""
      }
      """
    Then the response status should be 200

  Scenario: Receive unsubscribe event
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "unsubscribe",
        "email": "unsub@example.com",
        "X-Mailin-custom": ""
      }
      """
    Then the response status should be 200

  Scenario: Receive open event
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "open",
        "email": "opener@example.com",
        "X-Mailin-custom": ""
      }
      """
    Then the response status should be 200

  Scenario: Receive click event
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "click",
        "email": "clicker@example.com",
        "X-Mailin-custom": ""
      }
      """
    Then the response status should be 200

  Scenario: Receive request event
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "request",
        "email": "requested@example.com",
        "X-Mailin-custom": ""
      }
      """
    Then the response status should be 200

  Scenario: Webhook with empty body returns 200
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo"
    Then the response status should be 200

  Scenario: Webhook with missing email field returns 200
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {"event": "delivered"}
      """
    Then the response status should be 200

  Scenario: Webhook with unknown event type returns 200
    Given I am authenticated as webhook service
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {
        "event": "unknown_event",
        "email": "user@example.com"
      }
      """
    Then the response status should be 200

  Scenario: Webhook with invalid JSON returns 400
    Given I am authenticated as webhook service
    When I send a raw POST to "/api/v1/webhooks/brevo" with body "not json" and header "Content-Type: application/json"
    Then the response status should be 400

  Scenario: Webhook without authentication returns 401
    Given I am not authenticated
    When I send a POST to "/api/v1/webhooks/brevo"
    Then the response status should be 401

  # ── Effect on the stored emails (signature checking enabled) ──────────────

  Scenario: A signed delivered event marks the email as delivered
    Given I am authenticated as webhook service
    And the setting "webhook_hmac_secret" is "bdd-hmac-secret"
    And a "sent" email to "recipient@example.com" via "brevo" stored as "email_id"
    When Brevo sends a signed "delivered" event for "email_id"
    Then the response status should be 200
    And the stored email "email_id" should have status "delivered"

  Scenario: A signed hard bounce marks the email as bounced with the reason
    Given I am authenticated as webhook service
    And the setting "webhook_hmac_secret" is "bdd-hmac-secret"
    And a "sent" email to "bounced@example.com" via "brevo" stored as "email_id"
    When Brevo sends a signed "hard_bounce" event with reason "User unknown" for "email_id"
    Then the response status should be 200
    And the stored email "email_id" should have status "bounced"
    And the stored email "email_id" should have error "User unknown"

  Scenario: A complaint marks the email as bounced
    Given I am authenticated as webhook service
    And the setting "webhook_hmac_secret" is "bdd-hmac-secret"
    And a "delivered" email to "angry@example.com" via "brevo" stored as "email_id"
    When Brevo sends a signed "complaint" event for "email_id"
    Then the response status should be 200
    And the stored email "email_id" should have status "bounced"
    And the stored email "email_id" should have error "Spam complaint"

  Scenario: An event with a forged signature is rejected
    Given I am authenticated as webhook service
    And the setting "webhook_hmac_secret" is "bdd-hmac-secret"
    And a "sent" email to "recipient@example.com" via "brevo" stored as "email_id"
    When Brevo sends a "delivered" event for "email_id" with a forged signature
    Then the response status should be 401
    And the stored email "email_id" should have status "sent"

  Scenario: An event without signature is rejected when a secret is configured
    Given I am authenticated as webhook service
    And the setting "webhook_hmac_secret" is "bdd-hmac-secret"
    And a "sent" email to "recipient@example.com" via "brevo" stored as "email_id"
    When Brevo sends a "delivered" event for "email_id" without signature
    Then the response status should be 401
    And the stored email "email_id" should have status "sent"

  Scenario: Events need the webhooks scope
    Given I am authenticated with scopes "mailler:read mailler:send"
    When I send a POST to "/api/v1/webhooks/brevo" with
      """
      {"event": "delivered", "email": "recipient@example.com"}
      """
    Then the response status should be 403
