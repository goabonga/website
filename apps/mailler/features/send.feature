Feature: Send emails
  An email is stored, queued on the Celery worker and delivered through the
  chosen provider. Delivery updates the email status and the provider
  statistics.

  Scenario: Sending an email queues it for delivery
    Given I am authenticated
    When I send a POST to "/api/v1/send" with
      """
      {
        "to_email": "recipient@example.com",
        "to_name": "John Doe",
        "subject": "Hello from BDD",
        "html_content": "<h1>Hello!</h1>",
        "text_content": "Hello!",
        "provider": "brevo"
      }
      """
    Then the response status should be 200
    And the response JSON "status" should be "queued"
    And the response JSON should contain "id"
    And the response JSON should contain "task_id"
    And the email to "recipient@example.com" should be stored with status "pending"
    And the task "send_email_task" should have been queued 1 time

  Scenario: The queued task targets the stored email
    Given I am authenticated
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "provider": "brevo"}
      """
    Then the response status should be 200
    And I store the response "id" as "email_id"
    And the task "send_email_task" should have been queued for "email_id"

  Scenario: The default sender is applied when none is given
    Given I am authenticated
    And the setting "default_from" is "noreply@example.org"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "provider": "brevo"}
      """
    Then the response status should be 200
    And the email to "recipient@example.com" should have sender "noreply@example.org"

  Scenario: An email without any sender is refused
    Given I am authenticated
    And the setting "default_from" is empty
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "provider": "brevo"}
      """
    Then the response status should be 422
    And the response should contain "No sender address"
    And the task "send_email_task" should have been queued 0 time

  Scenario: The email is recorded for the client of the token
    Given I am authenticated as client "app-one" with scopes "mailler:send mailler:read"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "provider": "brevo"}
      """
    Then the response status should be 200
    And the email to "recipient@example.com" should belong to client "app-one"

  Scenario: A custom sender overrides the default
    Given I am authenticated
    When I send a POST to "/api/v1/send" with
      """
      {
        "to_email": "recipient@example.com",
        "subject": "Custom sender",
        "html_content": "<p>Test</p>",
        "provider": "brevo",
        "from_email": "custom@example.com",
        "from_name": "Custom Sender",
        "reply_to": "replies@example.com"
      }
      """
    Then the response status should be 200
    And the email to "recipient@example.com" should have sender "custom@example.com"

  Scenario: Metadata is stored with the email
    Given I am authenticated
    When I send a POST to "/api/v1/send" with
      """
      {
        "to_email": "recipient@example.com",
        "subject": "With metadata",
        "html_content": "<p>Test</p>",
        "provider": "brevo",
        "metadata": {"campaign": "onboarding"}
      }
      """
    Then the response status should be 200
    And the email to "recipient@example.com" should have metadata "campaign" equal to "onboarding"

  Scenario: Required fields are validated
    Given I am authenticated
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com"}
      """
    Then the response status should be 422
    And no email should be stored

  Scenario: The recipient address is validated
    Given I am authenticated
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "not-an-email", "subject": "Hi", "html_content": "<p>Hi</p>", "provider": "brevo"}
      """
    Then the response status should be 422

  Scenario: An empty subject is rejected
    Given I am authenticated
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "", "html_content": "<p>Hi</p>", "provider": "brevo"}
      """
    Then the response status should be 422

  Scenario: Sending requires authentication
    Given I am not authenticated
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "provider": "brevo"}
      """
    Then the response status should be 401
    And no email should be stored

  Scenario: Sending requires the send scope
    Given I am authenticated with scopes "mailler:read"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "provider": "brevo"}
      """
    Then the response status should be 403
    And no email should be stored

  Scenario: The worker delivers a pending email
    Given a pending email to "recipient@example.com" via "brevo" stored as "email_id"
    And the provider accepts messages with id "msg-42"
    When the send task runs for "email_id"
    Then the task result "status" should be "sent"
    And the stored email "email_id" should have status "sent"
    And the stored email "email_id" should have provider message id "msg-42"
    And the provider should have received the message to "recipient@example.com"
    And the "brevo" statistics should count 1 "sent" email

  Scenario: An email that was already delivered is not sent twice
    Given a pending email to "recipient@example.com" via "brevo" stored as "email_id"
    And the provider accepts messages with id "msg-1"
    When the send task runs for "email_id"
    And the send task runs for "email_id"
    Then the task result "status" should be "sent"
    And the provider should have received the message to "recipient@example.com"

  Scenario: An email fails for good after the last retry
    Given a pending email to "recipient@example.com" via "brevo" stored as "email_id"
    And the stored email "email_id" has already failed 2 times
    And the provider rejects messages with "mailbox full"
    When the send task runs for "email_id"
    Then the task result "status" should be "failed"
    And the stored email "email_id" should have status "failed"
    And the stored email "email_id" should have error "mailbox full"
    And the "brevo" statistics should count 1 "failed" email

  Scenario: A provider that is not configured fails the email immediately
    Given a pending email to "recipient@example.com" via "brevo" stored as "email_id"
    When the send task runs for "email_id"
    Then the task result "status" should be "failed"
    And the stored email "email_id" should have error "not properly configured"
