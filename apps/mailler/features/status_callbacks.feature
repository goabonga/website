Feature: Status callbacks
  A client can register a callback URL and a secret: the service posts a
  signed JSON notification there when one of its emails is sent, delivered,
  bounced or fails, so the application needs no polling.

  Scenario: An administrator registers a callback
    Given I am authenticated as unregistered client "ops" with scopes "mailler:admin"
    When I send a POST to "/api/v1/clients" with
      """
      {
        "client_id": "app-one",
        "callback_url": "https://app-one.example/mailler/status",
        "callback_secret": "0123456789abcdef-secret"
      }
      """
    Then the response status should be 201
    And the response JSON "callback_url" should be "https://app-one.example/mailler/status"
    And the response JSON "has_callback_secret" should be true
    And the response should not contain "0123456789abcdef-secret"
    When I send a GET to "/api/v1/clients/app-one"
    Then the response JSON "has_callback_secret" should be true
    And the response should not contain "0123456789abcdef-secret"

  Scenario: Invalid callbacks are refused
    Given I am authenticated as unregistered client "ops" with scopes "mailler:admin"
    When I send a POST to "/api/v1/clients" with
      """
      {"client_id": "app-one", "callback_url": "http://app-one.example/hook", "callback_secret": "0123456789abcdef-secret"}
      """
    Then the response status should be 422
    When I send a POST to "/api/v1/clients" with
      """
      {"client_id": "app-one", "callback_url": "https://app-one.example/hook"}
      """
    Then the response status should be 422
    When I send a POST to "/api/v1/clients" with
      """
      {"client_id": "app-one", "callback_url": "https://app-one.example/hook", "callback_secret": "short"}
      """
    Then the response status should be 422
    When I send a GET to "/api/v1/clients/app-one"
    Then the response status should be 404

  Scenario: A callback cannot be left without its secret
    Given the following clients are registered
      | client_id |
      | app-one   |
    And I am authenticated as unregistered client "ops" with scopes "mailler:admin"
    When I send a PUT to "/api/v1/clients/app-one" with
      """
      {"callback_url": "https://app-one.example/hook"}
      """
    Then the response status should be 422
    When I send a PUT to "/api/v1/clients/app-one" with
      """
      {"callback_url": "https://app-one.example/hook", "callback_secret": "0123456789abcdef-secret"}
      """
    Then the response status should be 200
    And the response JSON "has_callback_secret" should be true

  Scenario: The client is notified when its email is sent
    Given the following clients are registered
      | client_id | callback_url                          | callback_secret         |
      | app-one   | https://app-one.example/mailler/status | 0123456789abcdef-secret |
    And the provider accepts messages with id "msg-1"
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>", "metadata": {"invitation": 42}}
      """
    Then the response status should be 200
    And I store the response "id" as "email_id"
    And the task "deliver_status_callback" should have been queued 0 time
    When the send task runs for "email_id"
    Then the task "deliver_status_callback" should have been queued 1 time
    When the callback task runs for the email to "newcomer@example.com"
    Then the callback task should have delivered the notification
    And the client endpoint should have received 1 notification
    And the notification should be posted to "https://app-one.example/mailler/status"
    And the notification should be signed with the secret "0123456789abcdef-secret"
    And the notification field "event" should be "email.status"
    And the notification field "status" should be "sent"
    And the notification field "client_id" should be "app-one"
    And the notification field "to_email" should be "newcomer@example.com"
    And the notification field "provider_message_id" should be "msg-1"

  Scenario: The client is notified when its email fails for good
    Given the following clients are registered
      | client_id | callback_url                          | callback_secret         |
      | app-one   | https://app-one.example/mailler/status | 0123456789abcdef-secret |
    And the provider rejects messages with "mailbox full"
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then I store the response "id" as "email_id"
    Given the stored email "email_id" has already failed 2 times
    When the send task runs for "email_id"
    And the callback task runs for the email to "newcomer@example.com"
    Then the notification field "status" should be "failed"
    And the notification field "error_message" should be "mailbox full"

  Scenario: Nothing is queued for a client without a callback
    Given the provider accepts messages with id "msg-1"
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then I store the response "id" as "email_id"
    When the send task runs for "email_id"
    Then the task "deliver_status_callback" should have been queued 0 time

  Scenario: A refused notification is delivered again later
    Given the following clients are registered
      | client_id | callback_url                          | callback_secret         |
      | app-one   | https://app-one.example/mailler/status | 0123456789abcdef-secret |
    And the provider accepts messages with id "msg-1"
    And the client endpoint answers 503
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then I store the response "id" as "email_id"
    When the send task runs for "email_id"
    And the callback task runs for the email to "newcomer@example.com"
    Then the callback task should be delivered again later
    And the client endpoint should have received 1 notification
