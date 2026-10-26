Feature: Sending from a template
  A request can name one of the templates of its client instead of carrying
  the content: the service renders the subject, the HTML and the plain text
  from the variables, so an application sends a transactional email in one
  call.

  Background:
    Given a directory with the templates
      | slug                 | subject                   | extra                                        | mjml                                                                                                                                                  |
      | workspace_invitation | {{ inviter }} invites you | {"plain_text": "Join %workspace% at %link%"} | <mjml><mj-body><mj-section><mj-column><mj-text>{{ inviter }} invites you to {{ workspace }}: {{ link }}</mj-text></mj-column></mj-section></mj-body></mjml> |
      | plain_notice         | A notice for {{ name }}   | {}                                           |                                                                                                                                                       |
    And the following clients are registered
      | client_id | from_email            | from_name | allowed_providers | default_provider |
      | app-one   | hello@app-one.example | App One   | brevo             | brevo            |
      | app-two   | hello@app-two.example | App Two   | brevo             | brevo            |
    And I run the command line: templates import --client-id app-one {templates_dir}

  Scenario: One call sends a rendered email
    Given I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {
        "to_email": "newcomer@example.com",
        "template_slug": "workspace_invitation",
        "variables": {"inviter": "Ann", "workspace": "Acme", "link": "https://app.example/join"}
      }
      """
    Then the response status should be 200
    And the response JSON "status" should be "queued"
    And the response JSON "missing_variables" should have 0 entries
    And the email to "newcomer@example.com" should have subject "Ann invites you"
    And the email to "newcomer@example.com" should have plain text "Join Acme at https://app.example/join"
    And the email to "newcomer@example.com" should have sender "hello@app-one.example"
    And the email to "newcomer@example.com" should use provider "brevo"
    And the email to "newcomer@example.com" should have metadata "template_slug" equal to "workspace_invitation"
    And the task "send_email_task" should have been queued 1 time

  Scenario: The values are escaped in the HTML but not in the subject
    Given I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {
        "to_email": "newcomer@example.com",
        "template_slug": "workspace_invitation",
        "variables": {"inviter": "Tom & <b>Jerry</b>", "workspace": "Acme", "link": "x"}
      }
      """
    Then the response status should be 200
    And the email to "newcomer@example.com" should have subject "Tom & <b>Jerry</b> invites you"
    And the email to "newcomer@example.com" should have HTML containing "Tom &amp; &lt;b&gt;Jerry&lt;/b&gt;"
    And the email to "newcomer@example.com" should have HTML not containing "<b>Jerry</b>"

  Scenario: The plain text is derived from the HTML when the template has none
    Given I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "reader@example.com", "template_slug": "plain_notice", "variables": {"name": "Ann"}}
      """
    Then the response status should be 200
    And the email to "reader@example.com" should have plain text "Hello Ann"

  Scenario: The variables a request forgot are reported
    Given I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "newcomer@example.com", "template_slug": "workspace_invitation", "variables": {"inviter": "Ann"}}
      """
    Then the response status should be 200
    And the response JSON "missing_variables" should have 2 entries
    And the response JSON "missing_variables" should list "workspace"
    And the response JSON "missing_variables" should list "link"

  Scenario: Templates can be scheduled too
    Given I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/schedule" with
      """
      {"to_email": "later@example.com", "template_slug": "plain_notice", "variables": {"name": "Ann"}, "scheduled_at": "2030-01-01T10:00:00Z"}
      """
    Then the response status should be 200
    And the response JSON "status" should be "scheduled"
    And the email to "later@example.com" should have subject "A notice for Ann"
    And the email to "later@example.com" should be scheduled

  Scenario: An unknown template is not found
    Given I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "newcomer@example.com", "template_slug": "nope"}
      """
    Then the response status should be 404
    And no email should be stored

  Scenario: A client cannot send the template of another client
    Given I am authenticated as client "app-two" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "newcomer@example.com", "template_slug": "plain_notice", "variables": {"name": "Ann"}}
      """
    Then the response status should be 404
    And no email should be stored

  Scenario: Two clients can have a template with the same slug
    Given I run the command line: templates import --client-id app-two {templates_dir}
    And I am authenticated as client "app-two" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "other@example.com", "template_slug": "plain_notice", "variables": {"name": "Bob"}}
      """
    Then the response status should be 200
    And the email to "other@example.com" should have sender "hello@app-two.example"

  Scenario: Only active templates are sent
    Given I am authenticated as client "app-one" with scopes "mailler:send mailler:read mailler:write"
    When I send a GET to "/api/v1/templates/by-slug/plain_notice"
    Then I store the response "id" as "template_id"
    When I send a PUT to "/api/v1/templates/{template_id}" with
      """
      {"status": "draft"}
      """
    Then the response status should be 200
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "reader@example.com", "template_slug": "plain_notice", "variables": {"name": "Ann"}}
      """
    Then the response status should be 422
    And the response should contain "not active"
    When I send a PUT to "/api/v1/templates/{template_id}" with
      """
      {"status": "active"}
      """
    And I send a POST to "/api/v1/send" with
      """
      {"to_email": "reader@example.com", "template_slug": "plain_notice", "variables": {"name": "Ann"}}
      """
    Then the response status should be 200

  Scenario: A request carries either a template or the content
    Given I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "x@example.com", "template_slug": "plain_notice", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 422
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "x@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "variables": {"a": 1}}
      """
    Then the response status should be 422
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "x@example.com"}
      """
    Then the response status should be 422
    And no email should be stored

  Scenario: The sender rules apply to emails sent from a template
    Given I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "x@example.com", "template_slug": "plain_notice", "variables": {"name": "Ann"}, "from_email": "ceo@bank.example"}
      """
    Then the response status should be 403
    And no email should be stored

  Scenario: A template cannot reach Python internals
    Given I am authenticated as client "app-one" with scopes "mailler:send mailler:write mailler:read"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "hostile", "name": "Hostile", "subject_template": "Hi", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>{{ ''.__class__.__mro__ }}</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a PUT to "/api/v1/templates/{template_id}" with
      """
      {"status": "active"}
      """
    And I send a POST to "/api/v1/send" with
      """
      {"to_email": "x@example.com", "template_slug": "hostile"}
      """
    Then the response status should be 422
    And the response should contain "not allowed"
    And no email should be stored

  Scenario: Sending from a template needs the send scope
    Given I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "x@example.com", "template_slug": "plain_notice"}
      """
    Then the response status should be 403
