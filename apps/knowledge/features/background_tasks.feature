Feature: Background tasks
  As the operator of the platform
  I want emails and workspace deletions to be handled by a Celery worker
  So that web requests stay fast and deletions happen on schedule

  Scenario: The worker listens on its own queue
    Then the Celery application should use the queue "knowledge"
    And the Celery application should register the task "knowledge.tasks.send_email"

  Scenario: Periodic tasks are scheduled hourly
    Then the beat schedule should run "knowledge.tasks.process_scheduled_deletions" every 3600 seconds
    And the beat schedule should run "knowledge.tasks.send_deletion_reminders" every 3600 seconds

  Scenario: An email task sends the template through mailler
    Given a mailler service that accepts emails
    When the task sends the "workspace_invitation" email to "bob@example.test"
      | variable       | value                          |
      | workspace_name | Acme                           |
      | inviter_name   | Alice                          |
      | role           | member                         |
      | user_email     | bob@example.test               |
      | invitation_url | https://app.example.test/i/abc |
      | year           | 2026                           |
    Then the task should succeed
    And mailler should have been asked to send the template "workspace_invitation" to "bob@example.test"
    And the mailler request should carry the variable "invitation_url" set to "https://app.example.test/i/abc"

  Scenario: The deletion confirmation email carries the confirmation link
    Given a mailler service that accepts emails
    When the workspace deletion email task runs for "Acme" with the link "https://app.example.test/confirm/xyz"
    Then the task should succeed
    And mailler should have been asked to send the template "workspace_deletion" to "owner@example.test"
    And the mailler request should carry the variable "confirmation_url" set to "https://app.example.test/confirm/xyz"
    And the mailler request should carry the variable "workspace_name" set to "Acme"

  Scenario: An email whose template is not imported is reported without retry
    Given a mailler service that answers 404 "Template not found"
    When the task sends the "no_such_template" email to "bob@example.test"
      | variable | value |
    Then the task should fail with "Template not found"

  Scenario: An email is retried when mailler is down
    Given a mailler service that answers 503 "unavailable"
    When the task is run by a worker for "workspace_deleted" to "bob@example.test"
    Then the task should be retried with a delay of 60 seconds

  Scenario: Scheduled deletions that are due are executed
    Given a workspace "Acme" scheduled for deletion yesterday
    When the scheduled deletions task runs
    Then the workspace "Acme" should have been deleted
    And the deletion request should be completed
    And the task should report 1 deleted workspace

  Scenario: A reminder is sent the day before the deletion
    Given a workspace "Acme" scheduled for deletion in 12 hours
    When the deletion reminders task runs
    Then a reminder email should be queued for "Acme" with a cancellation link
    And the reminder should be marked as sent

  Scenario: No reminder is sent too early
    Given a workspace "Acme" scheduled for deletion in 10 days
    When the deletion reminders task runs
    Then no reminder email should be queued
