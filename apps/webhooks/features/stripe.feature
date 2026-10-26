Feature: Stripe webhook proxy
  As the webhooks service
  I want to receive Stripe webhooks
  So that I can forward them to the internal API

  Scenario: Forward a payment intent event
    When I send a POST request to "/webhooks/stripe" with body
      """
      {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_123"}}}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward a checkout session event
    When I send a POST request to "/webhooks/stripe" with body
      """
      {"type": "checkout.session.completed", "data": {"object": {"id": "cs_123"}}}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward an invoice event
    When I send a POST request to "/webhooks/stripe" with body
      """
      {"type": "invoice.paid", "data": {"object": {"id": "in_123"}}}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Empty body returns 200
    When I send an empty POST request to "/webhooks/stripe"
    Then the response status code should be 200
    And the internal API should not have been called

  Scenario: Forward Authorization header when token is configured
    Given the Stripe internal API token is "stripe-secret-token"
    When I send a POST request to "/webhooks/stripe" with body
      """
      {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_auth"}}}
      """
    Then the response status code should be 200
    And the internal API should have been called
    And the internal API should have received authorization "Bearer stripe-secret-token"

  Scenario: No Authorization header when token is not configured
    When I send a POST request to "/webhooks/stripe" with body
      """
      {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_noauth"}}}
      """
    Then the response status code should be 200
    And the internal API should have been called
    And the internal API should not have received authorization

  Scenario: Forward the Stripe signature to the internal API
    Given the request has header "Stripe-Signature" with value "t=1700000000,v1=abc"
    When I send a POST request to "/webhooks/stripe" with headers and body
      """
      {"type": "invoice.paid", "data": {"object": {"id": "in_sig"}}}
      """
    Then the response status code should be 200
    And the internal API should have received header "Stripe-Signature" with value "t=1700000000,v1=abc"

  Scenario: Forward the raw body to the Stripe internal endpoint
    When I send a POST request to "/webhooks/stripe" with body
      """
      {"type": "invoice.paid", "data": {"object": {"id": "in_raw"}}}
      """
    Then the internal API should have received path "/webhooks/stripe"
    And the internal API should have received the request body

  Scenario: Relay the status of the internal API
    Given the internal API answers with status 400
    When I send a POST request to "/webhooks/stripe" with body
      """
      {"type": "invoice.paid", "data": {"object": {"id": "in_bad"}}}
      """
    Then the response status code should be 400

  Scenario: Bad gateway when the internal API cannot be reached
    Given the internal API cannot be reached
    When I send a POST request to "/webhooks/stripe" with body
      """
      {"type": "invoice.paid", "data": {"object": {"id": "in_down"}}}
      """
    Then the response status code should be 502

  Scenario: Service unavailable when the internal API is not configured
    Given the Stripe internal API is not configured
    When I send a POST request to "/webhooks/stripe" with body
      """
      {"type": "invoice.paid", "data": {"object": {"id": "in_unconfigured"}}}
      """
    Then the response status code should be 503
    And the internal API should not have been called
