Feature: Email templates management
  As an admin user with email template permissions
  I want to create, view, edit, duplicate, and delete email templates
  So that I can manage reusable email designs with MJML

  Background:
    Given I am a super admin

  # ==========================================================================
  # List templates
  # ==========================================================================

  @email-templates
  Scenario: List email templates
    Given the templates API returns a list of templates
    When I send a GET request to "/email-templates"
    Then the response status code should be 200
    And the response should be HTML

  @email-templates
  Scenario: List email templates unauthenticated
    Given I am not authenticated
    When I send a GET request to "/email-templates"
    Then the response status code should be 302

  @email-templates
  Scenario: List email templates with search filter
    Given the templates API returns a list of templates
    When I send a GET request to "/email-templates?search=welcome"
    Then the response status code should be 200
    And the response should be HTML

  @email-templates
  Scenario: List email templates with status filter
    Given the templates API returns a list of templates
    When I send a GET request to "/email-templates?status=active"
    Then the response status code should be 200
    And the response should be HTML

  # ==========================================================================
  # New template form
  # ==========================================================================

  @email-templates
  Scenario: View new template form
    When I send a GET request to "/email-templates/new"
    Then the response status code should be 200
    And the response should be HTML

  # ==========================================================================
  # Create template
  # ==========================================================================

  @email-templates
  Scenario: Create a new template successfully
    Given creating a template via API succeeds
    When I send a POST request to "/email-templates/new" with form data
      | field            | value                       |
      | name             | Welcome Email               |
      | slug             | welcome-email               |
      | description      | A welcome email template    |
      | subject_template | Welcome %first_name%!       |
      | mjml_source      | <mjml><mj-body></mj-body></mjml> |
      | plain_text       | Welcome!                    |
      | status           | draft                       |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/email-templates"
    And I should be redirected to a URL containing "success=Template+created"

  @email-templates
  Scenario: Create a new template failure
    Given creating a template via API fails
    When I send a POST request to "/email-templates/new" with form data
      | field            | value               |
      | name             | Bad Template        |
      | subject_template | Subject             |
      | mjml_source      | <mjml></mjml>       |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+create+template"

  @email-templates
  Scenario: Create a template with auto-generated slug
    Given creating a template via API succeeds
    When I send a POST request to "/email-templates/new" with form data
      | field            | value                       |
      | name             | My Great Template           |
      | subject_template | Hello!                      |
      | mjml_source      | <mjml><mj-body></mj-body></mjml> |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Template+created"

  # ==========================================================================
  # Template detail
  # ==========================================================================

  @email-templates
  Scenario: View template detail
    Given a template exists via API with id 1
    When I send a GET request to "/email-templates/1"
    Then the response status code should be 200
    And the response should be HTML

  @email-templates
  Scenario: View template detail not found
    Given a template does not exist via API
    When I send a GET request to "/email-templates/999"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Template+not+found"

  # ==========================================================================
  # Edit template
  # ==========================================================================

  @email-templates
  Scenario: View template edit form
    Given a template exists via API with id 1
    When I send a GET request to "/email-templates/1/edit"
    Then the response status code should be 200
    And the response should be HTML

  @email-templates
  Scenario: Update a template successfully
    Given updating a template via API succeeds
    When I send a POST request to "/email-templates/1/edit" with form data
      | field            | value                       |
      | name             | Updated Template            |
      | description      | Updated description         |
      | subject_template | Updated subject             |
      | mjml_source      | <mjml><mj-body></mj-body></mjml> |
      | plain_text       | Updated plain text          |
      | status           | active                      |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/email-templates/1"
    And I should be redirected to a URL containing "success=Template+updated"

  @email-templates
  Scenario: Update a template failure
    Given updating a template via API fails
    When I send a POST request to "/email-templates/1/edit" with form data
      | field            | value                       |
      | name             | Updated Template            |
      | subject_template | Updated subject             |
      | mjml_source      | <mjml><mj-body></mj-body></mjml> |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+update+template"

  # ==========================================================================
  # Compile MJML (JSON endpoint)
  # ==========================================================================

  @email-templates
  Scenario: Compile MJML successfully
    Given compiling MJML via API succeeds
    When I send a POST request to "/email-templates/compile" with JSON body
      """
      {"mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hello</mj-text></mj-column></mj-section></mj-body></mjml>", "subject": "Test Subject"}
      """
    Then the response status code should be 200
    And the response should be valid JSON
    And the response JSON should have key "success"
    And the response JSON should have key "html"

  @email-templates
  Scenario: Compile MJML with errors
    Given compiling MJML via API returns errors
    When I send a POST request to "/email-templates/compile" with JSON body
      """
      {"mjml_source": "<invalid-mjml>"}
      """
    Then the response status code should be 200
    And the response should be valid JSON
    And the response JSON key "success" should equal "False"

  @email-templates
  Scenario: Compile MJML with empty source
    When I send a POST request to "/email-templates/compile" with JSON body
      """
      {"mjml_source": ""}
      """
    Then the response status code should be 400
    And the response should be valid JSON

  # ==========================================================================
  # Preview template (JSON endpoint)
  # ==========================================================================

  @email-templates
  Scenario: Preview template with sample data
    Given a template exists via API with id 1
    And rendering a template via API succeeds
    When I send a POST request to "/email-templates/1/preview" with JSON body
      """
      {"sample_data": {"first_name": "Alice", "email": "alice@test.com"}}
      """
    Then the response status code should be 200
    And the response should be valid JSON
    And the response JSON should have key "html"
    And the response JSON should have key "subject"

  @email-templates
  Scenario: Preview template not found
    Given rendering a template via API returns not found
    When I send a POST request to "/email-templates/999/preview" with JSON body
      """
      {"sample_data": {}}
      """
    Then the response status code should be 404
    And the response should be valid JSON

  # ==========================================================================
  # Duplicate template
  # ==========================================================================

  @email-templates
  Scenario: Duplicate a template successfully
    Given a template exists via API with id 1
    And duplicating a template via API succeeds
    When I send a POST request to "/email-templates/1/duplicate"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/email-templates/"
    And I should be redirected to a URL containing "success=Template+duplicated"

  @email-templates
  Scenario: Duplicate a template not found
    Given a template does not exist via API
    When I send a POST request to "/email-templates/999/duplicate"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Template+not+found"

  # ==========================================================================
  # Delete template
  # ==========================================================================

  @email-templates
  Scenario: Delete a template successfully
    Given deleting a template via API succeeds
    When I send a POST request to "/email-templates/1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Template+deleted"

  @email-templates
  Scenario: Delete a template failure
    Given deleting a template via API fails
    When I send a POST request to "/email-templates/1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+delete+template"

  # ==========================================================================
  # Bulk delete
  # ==========================================================================

  @email-templates
  Scenario: Bulk delete templates
    Given bulk deleting templates via API succeeds
    When I send a POST request to "/email-templates/bulk-delete" with form data
      | field        | value |
      | template_ids | 1     |
      | template_ids | 2     |
    Then the response status code should be 303
    And I should be redirected to a URL containing "template(s)+deleted+successfully"

  @email-templates
  Scenario: Bulk delete with no selection
    When I send a POST request to "/email-templates/bulk-delete" with form data
      | field | value |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=No+templates+selected"
