# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for email templates feature scenarios."""

from behave import given

# --- List templates mock ---


@given("the templates API returns a list of templates")
def step_templates_list(context):
    context.mock_mailler_templates.get_templates.return_value = {
        "items": [
            {
                "id": 1,
                "slug": "welcome-email",
                "name": "Welcome Email",
                "description": "A welcome email template",
                "subject_template": "Welcome %first_name%!",
                "status": "active",
                "created_at": "2024-01-15T12:00:00Z",
                "updated_at": "2024-01-15T12:00:00Z",
            }
        ],
        "total": 1,
        "pages": 1,
    }


# --- Create template ---


@given("creating a template via API succeeds")
def step_create_template_success(context):
    context.mock_mailler_templates.create_template.return_value = {
        "id": 10,
        "slug": "welcome-email",
        "name": "Welcome Email",
        "status": "draft",
    }


@given("creating a template via API fails")
def step_create_template_failure(context):
    context.mock_mailler_templates.create_template.return_value = None


# --- Template detail ---


@given("a template exists via API with id {template_id:d}")
def step_template_exists_api(context, template_id):
    context.mock_mailler_templates.get_template.return_value = {
        "id": template_id,
        "slug": "welcome-email",
        "name": "Welcome Email",
        "description": "A welcome email template",
        "subject_template": "Welcome %first_name%!",
        "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hello</mj-text></mj-column></mj-section></mj-body></mjml>",
        "html_compiled": "<html><body>Hello</body></html>",
        "plain_text": "Hello",
        "status": "active",
        "variables": ["first_name", "email"],
        "created_at": "2024-01-15T12:00:00Z",
        "updated_at": "2024-01-15T12:00:00Z",
    }


@given("a template does not exist via API")
def step_template_not_exists_api(context):
    context.mock_mailler_templates.get_template.return_value = None


# --- Update template ---


@given("updating a template via API succeeds")
def step_update_template_success(context):
    context.mock_mailler_templates.update_template.return_value = {
        "id": 1,
        "slug": "welcome-email",
        "name": "Updated Template",
        "status": "active",
    }


@given("updating a template via API fails")
def step_update_template_failure(context):
    context.mock_mailler_templates.update_template.return_value = None


# --- Compile MJML ---


@given("compiling MJML via API succeeds")
def step_compile_mjml_success(context):
    context.mock_mailler_templates.compile_mjml.return_value = {
        "html": "<html><body>Compiled HTML</body></html>",
        "errors": [],
    }


@given("compiling MJML via API returns errors")
def step_compile_mjml_errors(context):
    context.mock_mailler_templates.compile_mjml.return_value = {
        "html": "",
        "errors": ["Invalid MJML element"],
    }


# --- Preview / Render template ---


@given("rendering a template via API succeeds")
def step_render_template_success(context):
    context.mock_mailler_templates.render_template.return_value = {
        "html": "<html><body>Rendered with Alice</body></html>",
        "subject": "Welcome Alice!",
        "plain_text": "Welcome Alice!",
    }


@given("rendering a template via API returns not found")
def step_render_template_not_found(context):
    context.mock_mailler_templates.render_template.return_value = None


# --- Duplicate template ---


@given("duplicating a template via API succeeds")
def step_duplicate_template_success(context):
    # The duplicate route calls get_template (already mocked) then create_template
    context.mock_mailler_templates.create_template.return_value = {
        "id": 20,
        "slug": "welcome-email-copy",
        "name": "Welcome Email (Copy)",
        "status": "draft",
    }


# --- Delete template ---


@given("deleting a template via API succeeds")
def step_delete_template_success(context):
    context.mock_mailler_templates.delete_template.return_value = True


@given("deleting a template via API fails")
def step_delete_template_failure(context):
    context.mock_mailler_templates.delete_template.return_value = False


# --- Bulk delete ---


@given("bulk deleting templates via API succeeds")
def step_bulk_delete_templates_success(context):
    context.mock_mailler_templates.delete_template.return_value = True
