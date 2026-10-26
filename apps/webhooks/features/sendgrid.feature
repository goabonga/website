Feature: SendGrid webhook proxy
  As the webhooks service
  I want to receive SendGrid email event webhooks
  So that I can forward them to the internal API

  Scenario: Forward a bounce event
    When I send a POST request to "/webhooks/sendgrid" with body
      """
      [{"event": "bounce", "email": "bounce@example.com", "type": "permanent", "reason": "550 user unknown", "timestamp": 1700000000, "sg_message_id": "abc123"}]
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward a spam report event
    When I send a POST request to "/webhooks/sendgrid" with body
      """
      [{"event": "spamreport", "email": "spam@example.com", "timestamp": 1700000000, "sg_message_id": "abc456"}]
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward a delivered event
    When I send a POST request to "/webhooks/sendgrid" with body
      """
      [{"event": "delivered", "email": "user@example.com", "response": "250 OK", "timestamp": 1700000000, "sg_message_id": "abc789"}]
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward multiple events
    When I send a POST request to "/webhooks/sendgrid" with body
      """
      [{"event": "delivered", "email": "a@example.com", "timestamp": 1700000000}, {"event": "bounce", "email": "b@example.com", "type": "permanent", "timestamp": 1700000001}]
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Empty body returns 200
    When I send an empty POST request to "/webhooks/sendgrid"
    Then the response status code should be 200
    And the internal API should not have been called

  Scenario: Reject invalid signature when verification key is configured
    Given a SendGrid verification key is configured
    And the request has header "X-Twilio-Email-Event-Webhook-Signature" with value "invalid"
    And the request has header "X-Twilio-Email-Event-Webhook-Timestamp" with value "1700000000"
    When I send a POST request to "/webhooks/sendgrid" with headers and body
      """
      [{"event": "delivered", "email": "user@example.com"}]
      """
    Then the response status code should be 401
    And the internal API should not have been called

  Scenario: Reject a request without signature when verification key is configured
    Given a SendGrid verification key is configured
    When I send a POST request to "/webhooks/sendgrid" with body
      """
      [{"event": "delivered", "email": "user@example.com"}]
      """
    Then the response status code should be 401
    And the internal API should not have been called

  Scenario: Reject a signature made with another key
    Given a SendGrid verification key is configured
    When I send a SendGrid POST request signed with another key to "/webhooks/sendgrid" with body
      """
      [{"event": "delivered", "email": "user@example.com"}]
      """
    Then the response status code should be 401
    And the internal API should not have been called

  Scenario: Accept valid signature when verification key is configured
    Given a SendGrid verification key is configured
    When I send a SendGrid-signed POST request to "/webhooks/sendgrid" with body
      """
      [{"event": "delivered", "email": "user@example.com"}]
      """
    Then the response status code should be 200
    And the internal API should have been called
    And the internal API should have received header "X-Twilio-Email-Event-Webhook-Timestamp" with value "1700000000"

  Scenario: Forward Authorization header when token is configured
    Given the SendGrid internal API token is "sendgrid-secret-token"
    When I send a POST request to "/webhooks/sendgrid" with body
      """
      [{"event": "delivered", "email": "user@example.com"}]
      """
    Then the response status code should be 200
    And the internal API should have been called
    And the internal API should have received authorization "Bearer sendgrid-secret-token"

  Scenario: No Authorization header when token is not configured
    When I send a POST request to "/webhooks/sendgrid" with body
      """
      [{"event": "delivered", "email": "user@example.com"}]
      """
    Then the response status code should be 200
    And the internal API should have been called
    And the internal API should not have received authorization

  Scenario: Forward the raw body to the SendGrid internal endpoint
    When I send a POST request to "/webhooks/sendgrid" with body
      """
      [{"event": "delivered", "email": "user@example.com"}]
      """
    Then the internal API should have received path "/webhooks/sendgrid"
    And the internal API should have received the request body

  Scenario: Bad gateway when the internal API cannot be reached
    Given the internal API cannot be reached
    When I send a POST request to "/webhooks/sendgrid" with body
      """
      [{"event": "delivered", "email": "user@example.com"}]
      """
    Then the response status code should be 502

  Scenario: Service unavailable when the internal API is not configured
    Given the SendGrid internal API is not configured
    When I send a POST request to "/webhooks/sendgrid" with body
      """
      [{"event": "delivered", "email": "user@example.com"}]
      """
    Then the response status code should be 503
    And the internal API should not have been called
