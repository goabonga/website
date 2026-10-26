Feature: Idempotent sending
  A client that is not sure a request reached the service repeats it with the
  same Idempotency-Key header: the first email is returned and no second one
  is sent.

  Background:
    Given I am authenticated as client "app-one" with scopes "mailler:send mailler:read"

  Scenario: A repeated request returns the first email
    When I send a POST to "/api/v1/send" with the idempotency key "invite-42" and
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then the response status should be 200
    And I store the response "id" as "first"
    When I send a POST to "/api/v1/send" with the idempotency key "invite-42" and
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then the response status should be 200
    And the response JSON "id" should be the stored "first"
    And the response should contain "Already submitted"
    And 1 email should be stored for "newcomer@example.com"
    And the task "send_email_task" should have been queued 1 time

  Scenario: Requests without a key are not merged
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    And I send a POST to "/api/v1/send" with
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then 2 emails should be stored for "newcomer@example.com"

  Scenario: The same key means nothing to another client
    Given the following clients are registered
      | client_id | from_email            | default_provider |
      | app-two   | hello@app-two.example | brevo            |
    When I send a POST to "/api/v1/send" with the idempotency key "shared-key" and
      """
      {"to_email": "newcomer@example.com", "subject": "From one", "html_content": "<p>One</p>"}
      """
    Then the response status should be 200
    Given I am authenticated as client "app-two" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with the idempotency key "shared-key" and
      """
      {"to_email": "newcomer@example.com", "subject": "From two", "html_content": "<p>Two</p>"}
      """
    Then the response status should be 200
    And 2 emails should be stored for "newcomer@example.com"

  Scenario: A key cannot be reused for another recipient
    When I send a POST to "/api/v1/send" with the idempotency key "invite-42" and
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then the response status should be 200
    When I send a POST to "/api/v1/send" with the idempotency key "invite-42" and
      """
      {"to_email": "someone@else.example", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then the response status should be 422
    And the response should contain "already used for another request"
    And 1 email should be stored for "newcomer@example.com"
    And no email should be stored for "someone@else.example"

  Scenario: A scheduled email is returned again too
    When I send a POST to "/api/v1/schedule" with the idempotency key "digest-1" and
      """
      {"to_email": "reader@example.com", "subject": "Digest", "html_content": "<p>Digest</p>", "scheduled_at": "2030-01-01T10:00:00Z"}
      """
    Then the response status should be 200
    And the response JSON "status" should be "scheduled"
    And I store the response "id" as "first"
    When I send a POST to "/api/v1/schedule" with the idempotency key "digest-1" and
      """
      {"to_email": "reader@example.com", "subject": "Digest", "html_content": "<p>Digest</p>", "scheduled_at": "2030-01-01T10:00:00Z"}
      """
    Then the response status should be 200
    And the response JSON "status" should be "scheduled"
    And the response JSON "id" should be the stored "first"
    And 1 email should be stored for "reader@example.com"

  Scenario: A repeated request is not counted again by the limits
    Given the following clients are registered
      | client_id | rate_limit_per_minute |
      | app-one   | 1                     |
    When I send a POST to "/api/v1/send" with the idempotency key "once" and
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then the response status should be 200
    When I send a POST to "/api/v1/send" with the idempotency key "once" and
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then the response status should be 200
    When I send a POST to "/api/v1/send" with the idempotency key "twice" and
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then the response status should be 429

  Scenario: The key has a maximum length
    When I send a POST to "/api/v1/send" with the idempotency key "kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk" and
      """
      {"to_email": "newcomer@example.com", "subject": "Welcome", "html_content": "<p>Welcome</p>"}
      """
    Then the response status should be 422
    And no email should be stored
