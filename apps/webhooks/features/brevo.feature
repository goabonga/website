Feature: Brevo webhook relay
  As the webhooks service
  I want to receive Brevo webhook events
  So that I can forward them to the internal API

  Scenario: Forward a delivered event
    When I send a POST request to "/webhooks/brevo" with body
      """
      {"event": "delivered", "email": "user@example.com", "ts_event": 1700000000}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward a hard bounce event
    When I send a POST request to "/webhooks/brevo" with body
      """
      {"event": "hard_bounce", "email": "bounce@example.com", "reason": "unknown user"}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward a soft bounce event
    When I send a POST request to "/webhooks/brevo" with body
      """
      {"event": "soft_bounce", "email": "temp@example.com"}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward a complaint event
    When I send a POST request to "/webhooks/brevo" with body
      """
      {"event": "complaint", "email": "spam@example.com"}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Empty body returns 200
    When I send an empty POST request to "/webhooks/brevo"
    Then the response status code should be 200
    And the internal API should not have been called

  Scenario: Reject invalid signature when secret is configured
    Given the Brevo webhook secret is "test-secret"
    And the request has header "X-Sib-Webhook-Signature" with value "invalid-signature"
    When I send a POST request to "/webhooks/brevo" with headers and body
      """
      {"event": "delivered", "email": "user@example.com"}
      """
    Then the response status code should be 401
    And the internal API should not have been called

  Scenario: Accept valid signature when secret is configured
    Given the Brevo webhook secret is "test-secret"
    When I send a Brevo-signed POST request to "/webhooks/brevo" with body
      """
      {"event": "delivered", "email": "user@example.com"}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward Authorization header when token is configured
    Given the Brevo internal API token is "brevo-secret-token"
    When I send a POST request to "/webhooks/brevo" with body
      """
      {"event": "delivered", "email": "user@example.com"}
      """
    Then the response status code should be 200
    And the internal API should have been called
    And the internal API should have received authorization "Bearer brevo-secret-token"

  Scenario: No Authorization header when token is not configured
    When I send a POST request to "/webhooks/brevo" with body
      """
      {"event": "delivered", "email": "user@example.com"}
      """
    Then the response status code should be 200
    And the internal API should have been called
    And the internal API should not have received authorization

  Scenario: Reject a request without signature when secret is configured
    Given the Brevo webhook secret is "test-secret"
    When I send a POST request to "/webhooks/brevo" with body
      """
      {"event": "delivered", "email": "user@example.com"}
      """
    Then the response status code should be 401
    And the internal API should not have been called

  Scenario: Forward the raw body to the Brevo internal endpoint
    When I send a POST request to "/webhooks/brevo" with body
      """
      {"event": "delivered", "email": "user@example.com"}
      """
    Then the internal API should have received path "/api/v1/webhooks/brevo"
    And the internal API should have received the request body

  Scenario: Relay the status of the internal API
    Given the internal API answers with status 202
    When I send a POST request to "/webhooks/brevo" with body
      """
      {"event": "delivered", "email": "user@example.com"}
      """
    Then the response status code should be 202

  Scenario: Bad gateway when the internal API cannot be reached
    Given the internal API cannot be reached
    When I send a POST request to "/webhooks/brevo" with body
      """
      {"event": "delivered", "email": "user@example.com"}
      """
    Then the response status code should be 502

  Scenario: Service unavailable when the internal API is not configured
    Given the Brevo internal API is not configured
    When I send a POST request to "/webhooks/brevo" with body
      """
      {"event": "delivered", "email": "user@example.com"}
      """
    Then the response status code should be 503
    And the internal API should not have been called
