Feature: Email Campaigns
  Manage email campaigns with full lifecycle: create, schedule, send, pause, resume.

  Background:
    Given I am authenticated

  # ── List ──────────────────────────────────────────────────────────────────

  Scenario: List campaigns when none exist
    When I send a GET to "/api/v1/campaigns"
    Then the response status should be 200
    And the response JSON "total" should be "0"

  Scenario: List campaigns with pagination
    When I send a GET to "/api/v1/campaigns?page=1&page_size=5"
    Then the response status should be 200
    And the response JSON should contain "items"
    And the response JSON should contain "pages"

  Scenario: List campaigns with search filter
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "January Newsletter", "description": "Monthly update"}
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/campaigns?search=January"
    Then the response status should be 200
    And the response JSON "total" should be "1"

  Scenario: List campaigns filtered by status
    When I send a GET to "/api/v1/campaigns?status=draft"
    Then the response status should be 200
    And the response JSON should contain "items"

  # ── Create ────────────────────────────────────────────────────────────────

  Scenario: Create a campaign
    When I send a POST to "/api/v1/campaigns" with
      """
      {
        "name": "Welcome Campaign",
        "description": "Onboarding emails"
      }
      """
    Then the response status should be 201
    And the response JSON "name" should be "Welcome Campaign"
    And the response JSON "status" should be "draft"
    And the response JSON should contain "id"
    And the response JSON should contain "stats"

  Scenario: Create campaign with all fields
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "campaign-tpl",
        "name": "Campaign Template",
        "subject_template": "Hello {{ name }}",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi {{ name }}</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "campaign-group", "name": "Campaign Group"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a POST to "/api/v1/campaigns" with
      """
      {
        "name": "Full Campaign",
        "description": "All fields set",
        "template_id": {template_id},
        "group_id": {group_id},
        "from_name": "Mailler",
        "from_email": "noreply@example.com",
        "reply_to": "replies@example.com",
        "provider": "brevo",
        "subject_override": "Custom Subject"
      }
      """
    Then the response status should be 201
    And the response JSON "name" should be "Full Campaign"

  # ── Get ───────────────────────────────────────────────────────────────────

  Scenario: Get campaign by ID
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Get Me"}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a GET to "/api/v1/campaigns/{campaign_id}"
    Then the response status should be 200
    And the response JSON "name" should be "Get Me"
    And the response JSON should contain "stats"

  Scenario: Get campaign returns 404 for unknown ID
    When I send a GET to "/api/v1/campaigns/99999"
    Then the response status should be 404

  # ── Update ────────────────────────────────────────────────────────────────

  Scenario: Update a campaign
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Original Campaign"}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a PUT to "/api/v1/campaigns/{campaign_id}" with
      """
      {"name": "Updated Campaign", "description": "Now with description"}
      """
    Then the response status should be 200
    And the response JSON "name" should be "Updated Campaign"

  Scenario: Update non-existent campaign returns 404
    When I send a PUT to "/api/v1/campaigns/99999" with
      """
      {"name": "Ghost"}
      """
    Then the response status should be 404

  # ── Delete ────────────────────────────────────────────────────────────────

  Scenario: Delete a campaign
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Deletable Campaign"}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a DELETE to "/api/v1/campaigns/{campaign_id}"
    Then the response status should be 204
    When I send a GET to "/api/v1/campaigns/{campaign_id}"
    Then the response status should be 404

  Scenario: Delete non-existent campaign returns 404
    When I send a DELETE to "/api/v1/campaigns/99999"
    Then the response status should be 404

  # ── Schedule ──────────────────────────────────────────────────────────────

  Scenario: Schedule a campaign
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "sched-campaign-tpl",
        "name": "Schedule Campaign Template",
        "subject_template": "Scheduled",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "sched-group", "name": "Schedule Group"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a POST to "/api/v1/campaigns" with
      """
      {
        "name": "Scheduled Campaign",
        "template_id": {template_id},
        "group_id": {group_id}
      }
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/schedule" with
      """
      {"scheduled_at": "2099-12-31T23:59:59Z"}
      """
    Then the response status should be 200
    And the response JSON "status" should be "scheduled"
    And the response JSON should contain "scheduled_at"

  Scenario: Schedule campaign without template fails
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "No Template Campaign"}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/schedule" with
      """
      {"scheduled_at": "2099-12-31T23:59:59Z"}
      """
    Then the response status should be 400

  # ── Send ──────────────────────────────────────────────────────────────────

  Scenario: Start sending a campaign
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "send-campaign-tpl",
        "name": "Send Campaign Template",
        "subject_template": "Hello",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "send-group", "name": "Send Group"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "campaign-recipient@example.com", "first_name": "Recipient"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a POST to "/api/v1/contact-groups/{group_id}/contacts" with
      """
      {"contact_ids": ["{contact_id}"]}
      """
    Then the response status should be 200
    When I send a POST to "/api/v1/campaigns" with
      """
      {
        "name": "Sending Campaign",
        "template_id": {template_id},
        "group_id": {group_id}
      }
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/send"
    Then the response status should be 200
    And the response JSON should contain "task_id"
    And the response JSON should contain "total_recipients"

  Scenario: Send campaign without group fails
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "send-no-group-tpl",
        "name": "No Group Template",
        "subject_template": "Hello",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "No Group Campaign", "template_id": {template_id}}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/send"
    Then the response status should be 400

  # ── Pause ─────────────────────────────────────────────────────────────────

  Scenario: Pause a non-sending campaign fails
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Not Sending"}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/pause"
    Then the response status should be 400

  # ── Resume ────────────────────────────────────────────────────────────────

  Scenario: Resume a non-paused campaign fails
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Not Paused"}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/resume"
    Then the response status should be 400

  # ── Preview ───────────────────────────────────────────────────────────────

  Scenario: Preview a campaign
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "preview-tpl",
        "name": "Preview Template",
        "subject_template": "Preview subject",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Preview content</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Preview Campaign", "template_id": {template_id}}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a GET to "/api/v1/campaigns/{campaign_id}/preview"
    Then the response status should be 200
    And the response JSON should contain "subject"
    And the response JSON should contain "html"
    And the response JSON should contain "recipient_count"

  Scenario: Preview campaign without template fails
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "No Template Preview"}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a GET to "/api/v1/campaigns/{campaign_id}/preview"
    Then the response status should be 400

  # ── Sends ─────────────────────────────────────────────────────────────────

  Scenario: List campaign sends
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Sends List Campaign"}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a GET to "/api/v1/campaigns/{campaign_id}/sends"
    Then the response status should be 200
    And the response JSON should contain "items"
    And the response JSON should contain "total"

  Scenario: List sends for non-existent campaign returns 404
    When I send a GET to "/api/v1/campaigns/99999/sends"
    Then the response status should be 404

  # ── Auth ──────────────────────────────────────────────────────────────────

  Scenario: Campaign endpoints require authentication
    Given I am not authenticated
    When I send a GET to "/api/v1/campaigns"
    Then the response status should be 401

  # ── Scopes ────────────────────────────────────────────────────────────────

  Scenario: A read-only token cannot create campaigns
    Given I am authenticated with scopes "mailler:read"
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Forbidden"}
      """
    Then the response status should be 403

  Scenario: Starting a campaign requires the send scope
    Given I am authenticated with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/campaigns/1/send"
    Then the response status should be 403

  # ── Worker ────────────────────────────────────────────────────────────────

  Scenario: Running a campaign creates one personalised email per active contact
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "run-tpl",
        "name": "Run template",
        "subject_template": "Hello {{ first_name }}",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi {{ first_name }}</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "run-group", "name": "Run group"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a POST to "/api/v1/contacts/bulk" with
      """
      {"contacts": [
        {"email": "ann@example.com", "first_name": "Ann"},
        {"email": "bob@example.com", "first_name": "Bob"},
        {"email": "gone@example.com", "first_name": "Gone"}
      ]}
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/contacts?search=gone"
    Then the response status should be 200
    And I store the first item "id" as "gone_id"
    When I send a POST to "/api/v1/contacts/{gone_id}/unsubscribe"
    Then the response status should be 200
    When I send a GET to "/api/v1/contacts?status=active"
    Then the response status should be 200
    And I add all listed contacts to the group "group_id"
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Run campaign", "template_id": {template_id}, "group_id": {group_id}, "provider": "brevo"}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/send"
    Then the response status should be 200
    And the response JSON "total_recipients" should be "2"
    When the campaign task runs for "campaign_id"
    Then the task result "queued" should be "2"
    And the email to "ann@example.com" should have subject "Hello Ann"
    And the email to "bob@example.com" should have subject "Hello Bob"
    And the email to "ann@example.com" should belong to client "bdd-client"
    And no email should be stored for "gone@example.com"
    And the task "send_email_task" should have been queued 2 times
    When I send a GET to "/api/v1/campaigns/{campaign_id}/sends"
    Then the response status should be 200
    And the response JSON "total" should be "2"

  Scenario: A campaign that is not sending is skipped by the worker
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Idle campaign"}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When the campaign task runs for "campaign_id"
    Then the task result "skipped" should be "True"

  Scenario: The scheduler starts due campaigns
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "due-tpl",
        "name": "Due template",
        "subject_template": "Due",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "due-group", "name": "Due group"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "due@example.com"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a POST to "/api/v1/contact-groups/{group_id}/contacts" with
      """
      {"contact_ids": ["{contact_id}"]}
      """
    Then the response status should be 200
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Due campaign", "template_id": {template_id}, "group_id": {group_id}}
      """
    Then the response status should be 201
    And I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/schedule" with
      """
      {"scheduled_at": "2099-12-31T23:59:59Z"}
      """
    Then the response status should be 200
    Given the campaign "campaign_id" is scheduled in the past
    When the scheduler starts the due campaigns
    Then the task result "started" should be "1"
    And the task "send_campaign_task" should have been queued 1 time
    When I send a GET to "/api/v1/campaigns/{campaign_id}"
    Then the response JSON "status" should be "sending"

  # ── Sender, provider and isolation ────────────────────────────────────────

  Scenario: The platform provider is used when a campaign names none
    Given the setting "default_provider" is "platform-provider"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "fallback-tpl", "name": "Fallback", "subject_template": "Hello", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then I store the response "id" as "template_id"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "fallback-group", "name": "Fallback"}
      """
    Then I store the response "id" as "group_id"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "fallback@example.com"}
      """
    Then I store the response "id" as "contact_id"
    When I send a POST to "/api/v1/contact-groups/{group_id}/contacts" with
      """
      {"contact_ids": ["{contact_id}"]}
      """
    And I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Fallback campaign", "template_id": {template_id}, "group_id": {group_id}}
      """
    Then I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/send"
    Then the response status should be 200
    When the campaign task runs for "campaign_id"
    Then the task result "queued" should be "1"
    And the email to "fallback@example.com" should use provider "platform-provider"
    And the email to "fallback@example.com" should have sender "sender@bdd.example"

  Scenario: A campaign without any provider fails instead of guessing one
    Given the setting "default_provider" is empty
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "noprov-tpl", "name": "No provider", "subject_template": "Hello", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then I store the response "id" as "template_id"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "noprov-group", "name": "No provider"}
      """
    Then I store the response "id" as "group_id"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "noprov@example.com"}
      """
    Then I store the response "id" as "contact_id"
    When I send a POST to "/api/v1/contact-groups/{group_id}/contacts" with
      """
      {"contact_ids": ["{contact_id}"]}
      """
    And I send a POST to "/api/v1/campaigns" with
      """
      {"name": "No provider campaign", "template_id": {template_id}, "group_id": {group_id}}
      """
    Then I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/send"
    And the campaign task runs for "campaign_id"
    Then the task result "error" should be "No sender or provider"
    And no email should be stored for "noprov@example.com"
    When I send a GET to "/api/v1/campaigns/{campaign_id}"
    Then the response JSON "status" should be "failed"

  Scenario: A client neither lists, reads, edits, sends nor deletes the campaigns of another client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write mailler:send"
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Private campaign"}
      """
    Then the response status should be 201
    And the response JSON "client_id" should be "app-one"
    And I store the response "id" as "campaign_id"
    Given I am authenticated as client "app-two" with scopes "mailler:read mailler:write mailler:send"
    When I send a GET to "/api/v1/campaigns"
    Then the response JSON "total" should be "0"
    When I send a GET to "/api/v1/campaigns/{campaign_id}"
    Then the response status should be 404
    When I send a PUT to "/api/v1/campaigns/{campaign_id}" with
      """
      {"name": "Hijacked"}
      """
    Then the response status should be 404
    When I send a POST to "/api/v1/campaigns/{campaign_id}/send"
    Then the response status should be 404
    When I send a POST to "/api/v1/campaigns/{campaign_id}/pause"
    Then the response status should be 404
    When I send a GET to "/api/v1/campaigns/{campaign_id}/sends"
    Then the response status should be 404
    When I send a DELETE to "/api/v1/campaigns/{campaign_id}"
    Then the response status should be 404

  Scenario: A campaign cannot use the template or the group of another client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "theirs", "name": "Theirs", "subject_template": "Hello", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then I store the response "id" as "template_id"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "theirs", "name": "Theirs"}
      """
    Then I store the response "id" as "group_id"
    Given I am authenticated as client "app-two" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Borrowed template", "template_id": {template_id}}
      """
    Then the response status should be 404
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Borrowed group", "group_id": {group_id}}
      """
    Then the response status should be 404

  Scenario: A campaign only mails the contacts of its own client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write mailler:send"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "welcome", "name": "Welcome", "subject_template": "Hello", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then I store the response "id" as "template_id"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "everyone", "name": "Everyone"}
      """
    Then I store the response "id" as "group_id"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "mine@example.com"}
      """
    Then I store the response "id" as "contact_id"
    When I send a POST to "/api/v1/contact-groups/{group_id}/contacts" with
      """
      {"contact_ids": ["{contact_id}"]}
      """
    Then the response status should be 200
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Mine", "template_id": {template_id}, "group_id": {group_id}, "provider": "brevo"}
      """
    Then I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/send"
    And the campaign task runs for "campaign_id"
    Then the task result "queued" should be "1"
    And the email to "mine@example.com" should belong to client "app-one"
