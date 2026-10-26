Feature: Authorized clients
  Only registered, active clients can use the service. The record of a client
  fixes the sender identity and the providers it sends with, and the
  administrators manage the registry.

  # ── Registry administration ───────────────────────────────────────────────

  Scenario: An administrator registers a client
    Given I am authenticated as unregistered client "ops" with scopes "mailler:admin"
    When I send a POST to "/api/v1/clients" with
      """
      {
        "client_id": "app-one",
        "name": "Application one",
        "from_email": "no-reply@app-one.example",
        "from_name": "Application one",
        "reply_to": "support@app-one.example",
        "allowed_senders": [{"email": "alerts@app-one.example", "name": "Alerts"}],
        "allowed_providers": ["brevo", "ses"],
        "default_provider": "brevo"
      }
      """
    Then the response status should be 201
    And the response JSON "client_id" should be "app-one"
    And the response JSON "is_active" should be true
    And the response JSON "default_provider" should be "brevo"
    And the response JSON "allowed_providers" should have 2 entries
    When I send a GET to "/api/v1/clients/app-one"
    Then the response status should be 200
    And the response JSON "from_email" should be "no-reply@app-one.example"
    And the response JSON "allowed_senders" should have 1 entries

  Scenario: A client cannot be registered twice
    Given I am authenticated as unregistered client "ops" with scopes "mailler:admin"
    When I send a POST to "/api/v1/clients" with
      """
      {"client_id": "app-one"}
      """
    Then the response status should be 201
    When I send a POST to "/api/v1/clients" with
      """
      {"client_id": "app-one"}
      """
    Then the response status should be 409

  Scenario: Invalid registrations are refused
    Given I am authenticated as unregistered client "ops" with scopes "mailler:admin"
    When I send a POST to "/api/v1/clients" with
      """
      {"client_id": "app-one", "allowed_providers": ["carrier-pigeon"]}
      """
    Then the response status should be 422
    When I send a POST to "/api/v1/clients" with
      """
      {"client_id": "app-one", "from_email": "not-an-address"}
      """
    Then the response status should be 422
    When I send a GET to "/api/v1/clients/app-one"
    Then the response status should be 404

  Scenario: Clients are listed, filtered and updated
    Given the following clients are registered
      | client_id | is_active |
      | app-one   | yes       |
      | app-two   | no        |
    And I am authenticated as unregistered client "ops" with scopes "mailler:admin"
    When I send a GET to "/api/v1/clients"
    Then the response JSON "total" should be "2"
    When I send a GET to "/api/v1/clients?is_active=false"
    Then the response JSON "total" should be "1"
    And the response JSON "items" should include an entry with "client_id" equal to "app-two"
    When I send a GET to "/api/v1/clients?search=one"
    Then the response JSON "total" should be "1"
    When I send a PUT to "/api/v1/clients/app-two" with
      """
      {"is_active": true, "name": "Second application"}
      """
    Then the response status should be 200
    And the response JSON "is_active" should be true
    And the response JSON "name" should be "Second application"
    And the client "app-two" should be active

  Scenario: Updating an unknown client returns 404
    Given I am authenticated as unregistered client "ops" with scopes "mailler:admin"
    When I send a PUT to "/api/v1/clients/nope" with
      """
      {"name": "Nobody"}
      """
    Then the response status should be 404

  Scenario: The registry is for administrators only
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write mailler:send"
    When I send a GET to "/api/v1/clients"
    Then the response status should be 403
    When I send a POST to "/api/v1/clients" with
      """
      {"client_id": "app-two"}
      """
    Then the response status should be 403
    When I send a PUT to "/api/v1/clients/app-one" with
      """
      {"is_active": false}
      """
    Then the response status should be 403

  # ── The gate ──────────────────────────────────────────────────────────────

  Scenario: An unregistered client is refused everywhere
    Given I am authenticated as unregistered client "stranger" with scopes "mailler:send mailler:read mailler:write"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 403
    And the response should contain "not registered"
    And no email should be stored
    When I send a GET to "/api/v1/emails"
    Then the response status should be 403
    When I send a GET to "/api/v1/templates"
    Then the response status should be 403

  Scenario: A deactivated client is refused until it is activated again
    Given the following clients are registered
      | client_id | is_active |
      | app-one   | no        |
    And I am authenticated as client "app-one" with scopes "mailler:send mailler:read"
    When I send a GET to "/api/v1/emails"
    Then the response status should be 403
    And the response should contain "deactivated"
    Given the client "app-one" is activated
    When I send a GET to "/api/v1/emails"
    Then the response status should be 200

  Scenario: Deactivating a client through the API refuses it from then on
    Given I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/emails"
    Then the response status should be 200
    Given I am authenticated as unregistered client "ops" with scopes "mailler:admin"
    When I send a PUT to "/api/v1/clients/app-one" with
      """
      {"is_active": false}
      """
    Then the response status should be 200
    Given I am authenticated as client "app-one" with scopes "mailler:read"
    And the client "app-one" is deactivated
    When I send a GET to "/api/v1/emails"
    Then the response status should be 403

  Scenario: Administrators do not need a record
    Given I am authenticated as unregistered client "ops" with scopes "mailler:read mailler:admin"
    When I send a GET to "/api/v1/emails"
    Then the response status should be 200

  # ── The sender and the provider come from the record ──────────────────────

  Scenario: The record provides the sender, the reply-to and the provider
    Given the following clients are registered
      | client_id | from_email           | from_name | reply_to           | allowed_providers | default_provider |
      | app-one   | hello@app-one.example | App One   | help@app-one.example | brevo,ses         | brevo            |
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 200
    And the email to "recipient@example.com" should have sender "hello@app-one.example"
    And the email to "recipient@example.com" should have sender name "App One"
    And the email to "recipient@example.com" should have reply-to "help@app-one.example"
    And the email to "recipient@example.com" should use provider "brevo"

  Scenario: A client chooses among its identities and providers
    Given the following clients are registered
      | client_id | from_email            | from_name | allowed_senders                 | allowed_providers | default_provider |
      | app-one   | hello@app-one.example | App One   | alerts@app-one.example=Alerts   | brevo,ses         | brevo            |
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "from_email": "alerts@app-one.example", "provider": "ses"}
      """
    Then the response status should be 200
    And the email to "recipient@example.com" should have sender "alerts@app-one.example"
    And the email to "recipient@example.com" should have sender name "Alerts"
    And the email to "recipient@example.com" should use provider "ses"

  Scenario: A client cannot send as someone else
    Given the following clients are registered
      | client_id | from_email            | from_name | allowed_providers | default_provider |
      | app-one   | hello@app-one.example | App One   | brevo             | brevo            |
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "from_email": "ceo@bank.example"}
      """
    Then the response status should be 403
    And the response should contain "Sender address"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "from_name": "Your Bank"}
      """
    Then the response status should be 403
    And the response should contain "Sender name"
    And no email should be stored

  Scenario: A client cannot use a provider outside its record
    Given the following clients are registered
      | client_id | from_email            | allowed_providers | default_provider |
      | app-one   | hello@app-one.example | brevo             | brevo            |
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "provider": "sendgrid"}
      """
    Then the response status should be 403
    And the response should contain "Provider"
    And no email should be stored

  Scenario: A fixed reply-to cannot be replaced
    Given the following clients are registered
      | client_id | from_email            | reply_to             | default_provider |
      | app-one   | hello@app-one.example | help@app-one.example | brevo            |
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "reply_to": "phish@evil.example"}
      """
    Then the response status should be 403
    And the response should contain "Reply-to"

  Scenario: A client without a sender or a provider cannot send
    Given the following clients are registered
      | client_id | from_email            | default_provider |
      | nosender  |                       | brevo            |
      | noprov    | hello@app-one.example |                  |
    And I am authenticated as client "nosender" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 422
    And the response should contain "No sender address"
    Given I am authenticated as client "noprov" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 422
    And the response should contain "No provider"

  Scenario: Scheduled emails follow the same rules
    Given the following clients are registered
      | client_id | from_email            | allowed_providers | default_provider |
      | app-one   | hello@app-one.example | brevo             | brevo            |
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/schedule" with
      """
      {"to_email": "later@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "scheduled_at": "2030-01-01T10:00:00Z"}
      """
    Then the response status should be 200
    And the email to "later@example.com" should have sender "hello@app-one.example"
    When I send a POST to "/api/v1/schedule" with
      """
      {"to_email": "other@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "from_email": "ceo@bank.example", "scheduled_at": "2030-01-01T10:00:00Z"}
      """
    Then the response status should be 403

  Scenario: Campaigns cannot ask for an identity outside the record
    Given the following clients are registered
      | client_id | from_email            | allowed_providers | default_provider |
      | app-one   | hello@app-one.example | brevo             | brevo            |
    And I am authenticated as client "app-one" with scopes "mailler:write"
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Spoofed", "from_email": "ceo@bank.example"}
      """
    Then the response status should be 403
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Allowed", "from_email": "hello@app-one.example", "provider": "brevo"}
      """
    Then the response status should be 201

  Scenario: An administrator is not bound by a record
    Given I am authenticated as unregistered client "ops" with scopes "mailler:send mailler:admin"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "from_email": "ops@platform.example", "provider": "sendgrid"}
      """
    Then the response status should be 200
    And the email to "recipient@example.com" should have sender "ops@platform.example"
    And the email to "recipient@example.com" should use provider "sendgrid"

  # ── Queued work of a deactivated client ───────────────────────────────────

  Scenario: An email accepted before the client was deactivated is not sent
    Given the provider accepts messages with id "msg-1"
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "queued@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 200
    And I store the response "id" as "email_id"
    Given the client "app-one" is deactivated
    When the send task runs for "email_id"
    Then the task result "status" should be "failed"
    And the task result "error" should be "Client is deactivated"
    And the stored email "email_id" should have status "failed"

  Scenario: A campaign of a deactivated client is not run
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write mailler:send"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "tpl", "name": "Template", "subject_template": "Hello", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then I store the response "id" as "template_id"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "grp", "name": "Group"}
      """
    Then I store the response "id" as "group_id"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "ann@example.com"}
      """
    Then I store the response "id" as "contact_id"
    When I send a POST to "/api/v1/contact-groups/{group_id}/contacts" with
      """
      {"contact_ids": ["{contact_id}"]}
      """
    And I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Stopped", "template_id": {template_id}, "group_id": {group_id}}
      """
    Then I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/send"
    Then the response status should be 200
    Given the client "app-one" is deactivated
    When the campaign task runs for "campaign_id"
    Then the task result "error" should be "Client is deactivated"
    And no email should be stored for "ann@example.com"
