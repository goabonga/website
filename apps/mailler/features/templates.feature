Feature: Email Templates
  Manage MJML email templates with CRUD, compilation, and rendering.

  Background:
    Given I am authenticated

  # ── List ──────────────────────────────────────────────────────────────────

  Scenario: List templates when none exist
    When I send a GET to "/api/v1/templates"
    Then the response status should be 200
    And the response JSON "total" should be "0"

  Scenario: List templates with search filter
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "searchable-tpl",
        "name": "Searchable Template",
        "subject_template": "Hello {{ name }}",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/templates?search=Searchable"
    Then the response status should be 200
    And the response JSON "total" should be "1"

  Scenario: List templates with status filter
    When I send a GET to "/api/v1/templates?status=active"
    Then the response status should be 200
    And the response JSON should contain "items"

  # ── Create ────────────────────────────────────────────────────────────────

  Scenario: Create a template successfully
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "welcome-email",
        "name": "Welcome Email",
        "description": "Sent to new users",
        "subject_template": "Welcome, {{ first_name }}!",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hello {{ first_name }}</mj-text></mj-column></mj-section></mj-body></mjml>",
        "variables": ["first_name"],
        "metadata": {"category": "onboarding"}
      }
      """
    Then the response status should be 201
    And the response JSON "slug" should be "welcome-email"
    And the response JSON "name" should be "Welcome Email"
    And the response JSON should contain "html_compiled"
    And the response JSON should contain "id"

  Scenario: Create template with duplicate slug fails
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "unique-slug",
        "name": "First Template",
        "subject_template": "Subject",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "unique-slug",
        "name": "Duplicate Template",
        "subject_template": "Subject",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 409

  Scenario: Create template with invalid slug format fails
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "Invalid Slug!",
        "name": "Bad Slug",
        "subject_template": "Subject",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 422

  # ── Get ───────────────────────────────────────────────────────────────────

  Scenario: Get template by ID
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "get-by-id",
        "name": "Get By ID",
        "subject_template": "Subject",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a GET to "/api/v1/templates/{template_id}"
    Then the response status should be 200
    And the response JSON "slug" should be "get-by-id"

  Scenario: Get template by slug
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "by-slug-test",
        "name": "By Slug Test",
        "subject_template": "Subject",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/templates/by-slug/by-slug-test"
    Then the response status should be 200
    And the response JSON "name" should be "By Slug Test"

  Scenario: Get template returns 404 for unknown ID
    When I send a GET to "/api/v1/templates/99999"
    Then the response status should be 404

  Scenario: Get template by slug returns 404 for unknown slug
    When I send a GET to "/api/v1/templates/by-slug/nonexistent"
    Then the response status should be 404

  # ── Update ────────────────────────────────────────────────────────────────

  Scenario: Update a template
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "updatable",
        "name": "Original Name",
        "subject_template": "Original Subject",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a PUT to "/api/v1/templates/{template_id}" with
      """
      {
        "name": "Updated Name",
        "description": "Now with description"
      }
      """
    Then the response status should be 200
    And the response JSON "name" should be "Updated Name"

  Scenario: Update template status to archived
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "archivable",
        "name": "Will Archive",
        "subject_template": "Subject",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a PUT to "/api/v1/templates/{template_id}" with
      """
      {"status": "archived"}
      """
    Then the response status should be 200
    And the response JSON "status" should be "archived"

  Scenario: Update non-existent template returns 404
    When I send a PUT to "/api/v1/templates/99999" with
      """
      {"name": "Ghost"}
      """
    Then the response status should be 404

  # ── Delete ────────────────────────────────────────────────────────────────

  Scenario: Delete a template
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "deletable",
        "name": "Deletable",
        "subject_template": "Subject",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a DELETE to "/api/v1/templates/{template_id}"
    Then the response status should be 204
    When I send a GET to "/api/v1/templates/{template_id}"
    Then the response status should be 404

  Scenario: Delete non-existent template returns 404
    When I send a DELETE to "/api/v1/templates/99999"
    Then the response status should be 404

  # ── Compile ───────────────────────────────────────────────────────────────

  Scenario: Compile MJML to HTML
    When I send a POST to "/api/v1/templates/compile" with
      """
      {
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hello World</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 200
    And the response JSON should contain "html"

  # ── Render ────────────────────────────────────────────────────────────────

  Scenario: Render a template with variables
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "renderable",
        "name": "Renderable",
        "subject_template": "Hello {{ name }}",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Dear {{ name }}</mj-text></mj-column></mj-section></mj-body></mjml>",
        "variables": ["name"]
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a POST to "/api/v1/templates/{template_id}/render" with
      """
      {"variables": {"name": "Alice"}}
      """
    Then the response status should be 200
    And the response JSON should contain "subject"
    And the response JSON should contain "html"

  Scenario: Rendering escapes HTML values but leaves the subject and the plain text alone
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "escaping",
        "name": "Escaping",
        "subject_template": "Hello {{ name }}",
        "plain_text": "Hi %name%",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Dear {{ name }}</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a POST to "/api/v1/templates/{template_id}/render" with
      """
      {"variables": {"name": "Tom <b>&</b> Jerry"}}
      """
    Then the response status should be 200
    And the response JSON "subject" should be "Hello Tom <b>&</b> Jerry"
    And the response JSON "plain_text" should be "Hi Tom <b>&</b> Jerry"
    And the response should contain "Tom &lt;b&gt;&amp;&lt;/b&gt; Jerry"

  Scenario: A template cannot reach Python internals when rendered
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "hostile",
        "name": "Hostile",
        "subject_template": "{{ ''.__class__.__mro__ }}",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And I store the response "id" as "template_id"
    When I send a POST to "/api/v1/templates/{template_id}/render" with
      """
      {"variables": {}}
      """
    Then the response status should be 400
    And the response should contain "not allowed"

  Scenario: Slugs may contain underscores
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "workspace_invitation",
        "name": "Workspace invitation",
        "subject_template": "You are invited",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 201
    And the response JSON "slug" should be "workspace_invitation"
    When I send a GET to "/api/v1/templates/by-slug/workspace_invitation"
    Then the response status should be 200

  Scenario: Render non-existent template returns 404
    When I send a POST to "/api/v1/templates/99999/render" with
      """
      {"variables": {}}
      """
    Then the response status should be 404

  # ── Auth ──────────────────────────────────────────────────────────────────

  Scenario: Template endpoints require authentication
    Given I am not authenticated
    When I send a GET to "/api/v1/templates"
    Then the response status should be 401

  # ── Scopes ────────────────────────────────────────────────────────────────

  Scenario: A read-only token can list templates
    Given I am authenticated with scopes "mailler:read"
    When I send a GET to "/api/v1/templates"
    Then the response status should be 200

  Scenario: A read-only token cannot create templates
    Given I am authenticated with scopes "mailler:read"
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "forbidden",
        "name": "Forbidden",
        "subject_template": "Subject",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"
      }
      """
    Then the response status should be 403

  Scenario: Creating a template with invalid MJML fails
    When I send a POST to "/api/v1/templates" with
      """
      {
        "slug": "broken",
        "name": "Broken",
        "subject_template": "Subject",
        "mjml_source": "<mjml><mj-body><mj-unknown-tag></mj-body></mjml>"
      }
      """
    Then the response status should be 400

  # ── Isolation between clients ─────────────────────────────────────────────

  Scenario: The same slug can be used by two clients
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "workspace-invitation", "name": "One", "subject_template": "Subject", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>One</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then the response status should be 201
    And the response JSON "client_id" should be "app-one"
    Given I am authenticated as client "app-two" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "workspace-invitation", "name": "Two", "subject_template": "Subject", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Two</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/templates/by-slug/workspace-invitation"
    Then the response status should be 200
    And the response JSON "name" should be "Two"

  Scenario: A duplicate slug is refused inside one client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "dup", "name": "One", "subject_template": "Subject", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>One</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then the response status should be 201
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "dup", "name": "Again", "subject_template": "Subject", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>One</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then the response status should be 409

  Scenario: A client neither sees, reads, edits nor deletes the templates of another client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "private", "name": "Private", "subject_template": "Subject", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Secret</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then the response status should be 201
    And I store the response "id" as "tpl"
    Given I am authenticated as client "app-two" with scopes "mailler:read mailler:write"
    When I send a GET to "/api/v1/templates"
    Then the response JSON "total" should be "0"
    When I send a GET to "/api/v1/templates/{tpl}"
    Then the response status should be 404
    When I send a GET to "/api/v1/templates/by-slug/private"
    Then the response status should be 404
    When I send a PUT to "/api/v1/templates/{tpl}" with
      """
      {"name": "Hijacked"}
      """
    Then the response status should be 404
    When I send a POST to "/api/v1/templates/{tpl}/render" with
      """
      {"variables": {}}
      """
    Then the response status should be 404
    When I send a DELETE to "/api/v1/templates/{tpl}"
    Then the response status should be 404
    Given I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/templates/{tpl}"
    Then the response status should be 200
    And the response JSON "name" should be "Private"

  Scenario: A client cannot name another client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "forged", "client_id": "app-two", "name": "Forged", "subject_template": "Subject", "mjml_source": "<mjml><mj-body></mj-body></mjml>"}
      """
    Then the response status should be 403
    When I send a GET to "/api/v1/templates?client_id=app-two"
    Then the response status should be 403
    When I send a GET to "/api/v1/templates/by-slug/forged?client_id=app-two"
    Then the response status should be 403

  Scenario: An administrator manages the templates of any client
    Given I am authenticated as client "ops" with scopes "mailler:read mailler:write mailler:admin"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "seeded", "client_id": "app-one", "name": "Seeded", "subject_template": "Subject", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then the response status should be 201
    And the response JSON "client_id" should be "app-one"
    And I store the response "id" as "tpl"
    When I send a GET to "/api/v1/templates?client_id=app-two"
    Then the response JSON "total" should be "0"
    When I send a GET to "/api/v1/templates/by-slug/seeded?client_id=app-one"
    Then the response status should be 200
    When I send a DELETE to "/api/v1/templates/{tpl}"
    Then the response status should be 204
