Feature: Command line administration
  Operators register the clients and import their templates with the mailler
  command instead of calling the API.

  Scenario: Registering a client from the command line
    When I run the command line: clients register app-one --from-email no-reply@app-one.example --from-name "App One" --default-provider brevo --allowed-provider brevo
    Then the command should succeed
    And the command output should contain "Registered client 'app-one'"
    Given I am authenticated as unregistered client "ops" with scopes "mailler:admin"
    When I send a GET to "/api/v1/clients/app-one"
    Then the response status should be 200
    And the response JSON "from_email" should be "no-reply@app-one.example"
    And the response JSON "default_provider" should be "brevo"

  Scenario: A client registered from the command line can send
    When I run the command line: clients register app-one --from-email no-reply@app-one.example --default-provider brevo --allowed-provider brevo
    Then the command should succeed
    Given I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "recipient@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 200
    And the email to "recipient@example.com" should have sender "no-reply@app-one.example"

  Scenario: Invalid registrations are reported
    When I run the command line: clients register app-one --default-provider carrier-pigeon
    Then the command should fail with exit code 2
    And the command error should contain "Unknown provider"
    When I run the command line: clients show app-one
    Then the command should fail with exit code 1
    And the command error should contain "not registered"

  Scenario: Registering a client twice is refused
    When I run the command line: clients register app-one
    And I run the command line: clients register app-one
    Then the command should fail with exit code 1
    And the command error should contain "already registered"

  Scenario: Clients are listed, shown, updated and deactivated
    When I run the command line: clients register app-one --from-email a@one.example
    And I run the command line: clients update app-one --daily-quota 50 --reply-to help@one.example
    Then the command should succeed
    When I run the command line: clients show app-one
    Then the command output should contain "help@one.example"
    And the command output should contain "50"
    When I run the command line: clients deactivate app-one
    And I run the command line: clients list --inactive
    Then the command output should contain "app-one"
    Given I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/emails"
    Then the response status should be 403
    When I run the command line: clients activate app-one
    And I send a GET to "/api/v1/emails"
    Then the response status should be 200

  Scenario: Importing the templates of a client
    Given a directory with the templates
      | slug                 | subject                  | extra                            |
      | workspace_invitation | You are invited          | {"name": "Workspace invitation"} |
      | workspace_deleted    | Your workspace is gone   | {"plain_text": "Bye %name%"}     |
    When I run the command line: templates import --client-id app-one {templates_dir}
    Then the command should succeed
    And the command output should contain "2 new, 0 updated"
    Given I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/templates/by-slug/workspace_invitation"
    Then the response status should be 200
    And the response JSON "status" should be "active"
    And the response JSON "name" should be "Workspace invitation"
    And the response JSON "subject_template" should be "You are invited"
    When I send a GET to "/api/v1/templates"
    Then the response JSON "total" should be "2"
    Given I am authenticated as client "app-two" with scopes "mailler:read"
    When I send a GET to "/api/v1/templates"
    Then the response JSON "total" should be "0"

  Scenario: Importing again updates the templates
    Given a directory with the templates
      | slug    | subject |
      | welcome | First   |
    When I run the command line: templates import --client-id app-one {templates_dir}
    And I run the command line: templates import --client-id app-one {templates_dir}
    Then the command output should contain "0 new, 1 updated"
    When I run the command line: templates list --client-id app-one
    Then the command output should contain "welcome"

  Scenario: A dry run writes nothing
    Given a directory with the templates
      | slug    | subject |
      | welcome | Hello   |
    When I run the command line: templates import --client-id app-one --dry-run {templates_dir}
    Then the command output should contain "Would import 1 template(s)"
    When I run the command line: templates list --client-id app-one
    Then the command output should not contain "welcome"

  Scenario: Broken template files are reported
    Given a directory with the templates
      | slug    | subject | mjml                                                                         |
      | welcome | Hello   | <mjml><mj-body><mj-section><mj-column><mj-text>x</mj-column></mj-section></mj-body></mjml> |
    When I run the command line: templates import --client-id app-one {templates_dir}
    Then the command should fail with exit code 1
    And the command error should contain "welcome: MJML compilation failed"
