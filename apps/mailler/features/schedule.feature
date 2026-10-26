Feature: Schedule emails
  An email can be stored with a delivery time. Celery beat queues it once it
  is due, requeues emails that were never picked up, purges old emails and
  aggregates the daily statistics.

  Scenario: Scheduling an email stores it without queuing it
    Given I am authenticated
    When I send a POST to "/api/v1/schedule" with
      """
      {
        "to_email": "later@example.com",
        "subject": "Scheduled",
        "html_content": "<p>Later</p>",
        "provider": "brevo",
        "scheduled_at": "2030-01-01T10:00:00Z"
      }
      """
    Then the response status should be 200
    And the response JSON "status" should be "scheduled"
    And the response JSON should contain "id"
    And the email to "later@example.com" should be stored with status "pending"
    And the email to "later@example.com" should be scheduled
    And the task "send_email_task" should have been queued 0 times

  Scenario: A scheduled email without any sender is refused
    Given I am authenticated
    And the setting "default_from" is empty
    When I send a POST to "/api/v1/schedule" with
      """
      {"to_email": "later@example.com", "subject": "Scheduled", "html_content": "<p>Later</p>", "provider": "brevo", "scheduled_at": "2030-01-01T10:00:00Z"}
      """
    Then the response status should be 422
    And the response should contain "No sender address"

  Scenario: A scheduled email belongs to the client of the token
    Given I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/schedule" with
      """
      {"to_email": "later@example.com", "subject": "Scheduled", "html_content": "<p>Later</p>", "provider": "brevo", "scheduled_at": "2030-01-01T10:00:00Z"}
      """
    Then the response status should be 200
    And the email to "later@example.com" should belong to client "app-one"

  Scenario: The scheduled time is required
    Given I am authenticated
    When I send a POST to "/api/v1/schedule" with
      """
      {"to_email": "later@example.com", "subject": "Scheduled", "html_content": "<p>Later</p>", "provider": "brevo"}
      """
    Then the response status should be 422
    And no email should be stored

  Scenario: The scheduled time must be a date
    Given I am authenticated
    When I send a POST to "/api/v1/schedule" with
      """
      {"to_email": "later@example.com", "subject": "S", "html_content": "<p>L</p>", "provider": "brevo", "scheduled_at": "tomorrow"}
      """
    Then the response status should be 422

  Scenario: Scheduling requires authentication
    Given I am not authenticated
    When I send a POST to "/api/v1/schedule" with
      """
      {"to_email": "later@example.com", "subject": "S", "html_content": "<p>L</p>", "provider": "brevo", "scheduled_at": "2030-01-01T10:00:00Z"}
      """
    Then the response status should be 401

  Scenario: Scheduling requires the send scope
    Given I am authenticated with scopes "mailler:read"
    When I send a POST to "/api/v1/schedule" with
      """
      {"to_email": "later@example.com", "subject": "S", "html_content": "<p>L</p>", "provider": "brevo", "scheduled_at": "2030-01-01T10:00:00Z"}
      """
    Then the response status should be 403

  Scenario: Due emails are queued and future ones are left alone
    Given the following emails are stored
      | alias | to_email       | scheduled_in |
      | due   | due@example.com    | -5m          |
      | later | later@example.com  | +2h          |
    When the scheduler task "process_scheduled_emails" runs
    Then the task result "queued" should be "1"
    And the task "send_email_task" should have been queued for "due"
    And the task "send_email_task" should have been queued 1 time

  Scenario: Emails that are not pending are not queued again
    Given the following emails are stored
      | to_email         | status | scheduled_in |
      | sent@example.com | sent   | -5m          |
    When the scheduler task "process_scheduled_emails" runs
    Then the task result "queued" should be "0"

  Scenario: Immediate emails stuck in pending are requeued
    Given the following emails are stored
      | alias | to_email          | age |
      | stuck | stuck@example.com | 10m |
      | fresh | fresh@example.com | 1m  |
    When the scheduler task "requeue_stuck_emails" runs
    Then the task result "requeued" should be "1"
    And the task "send_email_task" should have been queued for "stuck"
    And the task "send_email_task" should have been queued 1 time

  Scenario: Scheduled emails are not treated as stuck
    Given the following emails are stored
      | to_email         | age | scheduled_in |
      | later@example.com | 1d  | +1d          |
    When the scheduler task "requeue_stuck_emails" runs
    Then the task result "requeued" should be "0"

  Scenario: Old emails are purged
    Given the following emails are stored
      | to_email         | age |
      | old@example.com  | 120d |
      | new@example.com  | 1d   |
    When the scheduler task "cleanup_old_emails" runs
    Then the task result "deleted" should be "1"
    And the email to "old@example.com" should no longer be stored
    And the email to "new@example.com" should still be stored

  Scenario: The retention period can be changed
    Given the following emails are stored
      | to_email        | age |
      | week@example.com | 8d  |
    When the scheduler task "cleanup_old_emails" runs with days=7
    Then the task result "deleted" should be "1"

  Scenario: The retention period comes from the settings
    Given the setting "email_retention_days" is 7
    And the following emails are stored
      | to_email         | age |
      | week@example.com | 8d  |
      | new@example.com  | 1d  |
    When the scheduler task "cleanup_old_emails" runs
    Then the task result "deleted" should be "1"
    And the email to "new@example.com" should still be stored

  Scenario: Yesterday's statistics are aggregated per provider
    Given the following emails are stored
      | to_email      | provider | status | age |
      | a@example.com | brevo    | sent   | 1d  |
      | b@example.com | brevo    | sent   | 1d  |
      | c@example.com | brevo    | failed | 1d  |
    When the scheduler task "aggregate_daily_stats" runs
    Then the "brevo" statistics should count 2 "sent" email
    And the "brevo" statistics should count 1 "failed" email
