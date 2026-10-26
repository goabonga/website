Feature: Email providers
  Emails are delivered through one of several providers. A provider is usable
  only when its credentials are configured, and the configured ones are
  listed by the API.

  Scenario: No provider is available without credentials
    Given I am authenticated
    When I send a GET to "/api/v1/providers"
    Then the response status should be 200
    And the response JSON "providers" should be
      """
      """

  Scenario: A provider with credentials is listed
    Given I am authenticated
    And the "brevo" provider is configured
    When I send a GET to "/api/v1/providers"
    Then the response status should be 200
    And the response JSON "providers" should contain "brevo"

  Scenario: Several configured providers are all listed
    Given I am authenticated
    And the "brevo" provider is configured
    And the "sendgrid" provider is configured
    And the "ses" provider is configured
    And the "protonmail" provider is configured
    When I send a GET to "/api/v1/providers"
    Then the response status should be 200
    And the response JSON "providers" should be
      """
      brevo
      sendgrid
      ses
      protonmail
      """

  Scenario: Listing providers requires authentication
    Given I am not authenticated
    When I send a GET to "/api/v1/providers"
    Then the response status should be 401

  Scenario: Listing providers requires the read scope
    Given I am authenticated with scopes "mailler:send"
    When I send a GET to "/api/v1/providers"
    Then the response status should be 403

  Scenario: Looking up a configured provider
    Given the "sendgrid" provider is configured
    When I look up the provider "sendgrid"
    Then the lookup should return a provider named "sendgrid"

  Scenario: Looking up a provider that is not configured
    When I look up the provider "ses"
    Then the lookup should fail with "not properly configured"

  Scenario: Looking up an unknown provider
    When I look up the provider "carrier-pigeon"
    Then the lookup should fail with "Unknown email provider"

  Scenario: An unsubscribe link signature is valid only for its address and client
    Given the signing secret is "bdd-secret"
    When I sign the unsubscribe link of "alice@example.com" for client "app-one"
    Then the signature should be valid for "alice@example.com" and client "app-one"
    And the signature should be rejected for "mallory@example.com" and client "app-one"
    And the signature should be rejected for "alice@example.com" and client "app-two"

  Scenario: The provider custom header carries the email identity and a signature
    Given the signing secret is "bdd-secret"
    When I build the Brevo custom header for email "11111111-2222-3333-4444-555555555555" to "bob@example.com"
    Then parsing the custom header should give email_id "11111111-2222-3333-4444-555555555555" and campaign_id "7"
