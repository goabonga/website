Feature: Inbound Emails
  Browse inbound emails received via IMAP polling.

  Background:
    Given I am authenticated

  # ── List ──────────────────────────────────────────────────────────────────

  Scenario: List inbound emails when none exist
    When I send a GET to "/api/v1/inbound/emails"
    Then the response status should be 200
    And the response JSON "total" should be "0"
    And the response JSON should contain "items"

  Scenario: List inbound emails with pagination
    When I send a GET to "/api/v1/inbound/emails?page=1&page_size=10"
    Then the response status should be 200
    And the response JSON should contain "items"
    And the response JSON should contain "total"
    And the response JSON should contain "pages"

  Scenario: List inbound emails filtered by status
    When I send a GET to "/api/v1/inbound/emails?status=received"
    Then the response status should be 200
    And the response JSON should contain "items"

  Scenario: List inbound emails filtered by sender
    When I send a GET to "/api/v1/inbound/emails?from_email=sender@example.com"
    Then the response status should be 200
    And the response JSON should contain "items"

  # ── Detail ────────────────────────────────────────────────────────────────

  Scenario: Get inbound email returns 404 for unknown ID
    When I send a GET to "/api/v1/inbound/emails/00000000-0000-0000-0000-000000000000"
    Then the response status should be 404

  # ── Attachment Download ───────────────────────────────────────────────────

  Scenario: Download attachment returns 404 for unknown token
    Given I am not authenticated
    When I send a GET to "/api/v1/inbound/attachments/00000000-0000-0000-0000-000000000000"
    Then the response status should be 404

  # ── Auth ──────────────────────────────────────────────────────────────────

  Scenario: Inbound email endpoints require authentication
    Given I am not authenticated
    When I send a GET to "/api/v1/inbound/emails"
    Then the response status should be 401

  Scenario: The shared inbound mailbox is not readable by a regular client
    Given I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/inbound/emails"
    Then the response status should be 403
    When I send a GET to "/api/v1/inbound/emails/00000000-0000-0000-0000-000000000000"
    Then the response status should be 403

  Scenario: An administrator reads the inbound mailbox
    Given I am authenticated as client "ops" with scopes "mailler:admin"
    When I send a GET to "/api/v1/inbound/emails"
    Then the response status should be 200

  Scenario: Attachment download is public (no auth needed)
    Given I am not authenticated
    When I send a GET to "/api/v1/inbound/attachments/00000000-0000-0000-0000-000000000000"
    Then the response status should be 404

  # ── Polling the mailbox ───────────────────────────────────────────────────

  Scenario: The inbound mailbox is not polled until it is configured
    Given inbound processing is enabled without a mailbox
    When the inbound poll task runs
    Then the task result "skipped" should be "True"
    And the task result "reason" should be "mailbox not configured"

  Scenario: A received message is stored and forwarded
    Given inbound processing is configured
    And the mailbox contains a message from "alice@example.org" titled "Hello there"
    When the inbound poll task runs
    Then the task result "processed" should be "1"
    And the task result "forwarded" should be "1"
    And 1 webhook delivery should have been attempted
    And 1 message should have been moved to the processed folder
    And the inbound email from "alice@example.org" should be stored with status "forwarded"
    When I send a GET to "/api/v1/inbound/emails"
    Then the response status should be 200
    And the response JSON "total" should be "1"
    And the response JSON "items" should include an entry with "subject" equal to "Hello there"

  Scenario: A stored message can be read
    Given inbound processing is configured
    And the mailbox contains a message from "alice@example.org" titled "Details please"
    When the inbound poll task runs
    And I send a GET to "/api/v1/inbound/emails"
    Then the response status should be 200
    And I store the first item "id" as "inbound_id"
    When I send a GET to "/api/v1/inbound/emails/{inbound_id}"
    Then the response status should be 200
    And the response JSON "from_email" should be "alice@example.org"
    And the response JSON "subject" should be "Details please"
    And the response JSON "status" should be "forwarded"

  Scenario: Stored messages can be filtered by sender and status
    Given inbound processing is configured
    And the mailbox contains a message from "alice@example.org" titled "From Alice"
    And the mailbox contains a message from "bob@example.org" titled "From Bob"
    When the inbound poll task runs
    And I send a GET to "/api/v1/inbound/emails?from_email=bob@example.org"
    Then the response status should be 200
    And the response JSON "total" should be "1"
    And the response JSON "items" should include an entry with "subject" equal to "From Bob"
    When I send a GET to "/api/v1/inbound/emails?status=failed"
    Then the response JSON "total" should be "0"

  Scenario: A failing webhook marks the message as failed and keeps it in the mailbox
    Given inbound processing is configured
    And the webhook target answers 500
    And the mailbox contains a message from "alice@example.org" titled "Will fail"
    When the inbound poll task runs
    Then the task result "failed" should be "1"
    And 0 messages should have been moved to the processed folder
    And the inbound email from "alice@example.org" should be stored with status "failed"

  Scenario: A failed message is forwarded again by the retry task
    Given inbound processing is configured
    And the webhook target answers 500
    And the mailbox contains a message from "alice@example.org" titled "Retry me"
    When the inbound poll task runs
    And the webhook target answers 200
    And the inbound retry task runs
    Then the task result "succeeded" should be "1"
    And the inbound email from "alice@example.org" should be stored with status "forwarded"

  Scenario: Polling does nothing when inbound processing is disabled
    Given the setting "inbound_enabled" is disabled
    When the inbound poll task runs
    Then the task result "skipped" should be "True"

  Scenario: Polling does nothing without a webhook URL
    Given inbound processing is configured
    And the setting "inbound_webhook_url" is empty
    When the inbound poll task runs
    Then the task result "reason" should be "no webhook URL"

  # ── Attachments ───────────────────────────────────────────────────────────

  Scenario: An attachment is saved and downloadable with its token
    Given inbound processing is configured
    And the mailbox contains a message from "alice@example.org" with subject "With file" and the attachment "note.txt" containing "attached text"
    When the inbound poll task runs
    Then I store the download token of the attachment "note.txt" as "token"
    Given I am not authenticated
    When I send a GET to "/api/v1/inbound/attachments/{token}"
    Then the response status should be 200
    And the response body should be "attached text"

  Scenario: An expired attachment can no longer be downloaded
    Given inbound processing is configured
    And the mailbox contains a message from "alice@example.org" with subject "With file" and the attachment "old.txt" containing "old text"
    When the inbound poll task runs
    Then I store the download token of the attachment "old.txt" as "token"
    Given every stored attachment has expired
    And I am not authenticated
    When I send a GET to "/api/v1/inbound/attachments/{token}"
    Then the response status should be 410

  Scenario: Expired attachments are removed by the cleanup task
    Given inbound processing is configured
    And the mailbox contains a message from "alice@example.org" with subject "With file" and the attachment "gone.txt" containing "gone text"
    When the inbound poll task runs
    Then I store the download token of the attachment "gone.txt" as "token"
    When every stored attachment has expired
    And the attachment cleanup task runs
    Then the task result "deleted_files" should be "1"
    And the task result "deleted_records" should be "1"
    Given I am not authenticated
    When I send a GET to "/api/v1/inbound/attachments/{token}"
    Then the response status should be 404

  Scenario: Reading inbound emails requires the read scope
    Given I am authenticated with scopes "mailler:send"
    When I send a GET to "/api/v1/inbound/emails"
    Then the response status should be 403
