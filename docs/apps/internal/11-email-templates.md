# Email templates

Authoring of the e-mail templates used by campaigns: an MJML editor with live HTML
preview. Templates are stored by the mailler service; the pages read and write them through the
mailler client, which also compiles MJML and renders previews on the service side.

## What it adds

| Module | Role |
| --- | --- |
| `internal/models/email_template.py` | Email template model for newsletter/email campaigns. |
| `internal/services/email_renderer.py` | Email rendering service with MJML compilation and Jinja2 templating. |
| `internal/routes/email_templates.py` | Email Templates CRUD routes with MJML editor. |

It also ships 3 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /email-templates | `email_templates:read` | List all email templates with pagination and filtering. |
| GET | /email-templates/new | `email_templates:write` | Show form to create a new email template. |
| POST | /email-templates/new | `email_templates:write` | Create a new email template. |
| GET | /email-templates/{template_id} | `email_templates:read` | View email template detail with preview. |
| GET | /email-templates/{template_id}/edit | `email_templates:write` | Show form to edit an email template. |
| POST | /email-templates/{template_id}/edit | `email_templates:write` | Update an email template. |
| POST | /email-templates/compile | `email_templates:read` | AJAX endpoint to compile MJML and return HTML preview. |
| POST | /email-templates/{template_id}/preview | `email_templates:read` | Preview email template with sample data. |
| POST | /email-templates/{template_id}/duplicate | `email_templates:write` | Duplicate an email template. |
| POST | /email-templates/bulk-delete | `email_templates:delete` | Delete multiple email templates. |
| POST | /email-templates/{template_id}/delete | `email_templates:delete` | Delete an email template. |

The list and detail pages request the whole `email_templates` resource plus `vpn:admin` and `billing:read` (navigation).

## Pages

- **List** (`/email-templates`): 20 per page, filterable by `status` (`draft`, `active`, `archived`) and
  by a search string.
- **Create and edit** (`/email-templates/new`, `/email-templates/{id}/edit`): name, slug (on creation),
  description, subject template, MJML source, optional plain-text version and status.
- **Detail** (`/email-templates/{id}`): the template with a rendered preview.
- **Compile** (`POST /email-templates/compile`): JSON endpoint behind the editor's live preview. It
  takes `mjml_source` (and optionally `subject` and `sample_data`) and answers with the compiled HTML or the MJML
  errors; an anonymous call gets a JSON `401`, an invalid body `400`.
- **Preview** (`POST /email-templates/{id}/preview`): renders a stored template with sample variables.
- **Duplicate** and **delete** (single and bulk; deletion needs `email_templates:delete`). A form cannot be nested in another one, so the Delete button of an edit form carries its own `formaction` and confirmation: nested, the browser would drop the inner form and the button would save the page instead. A failed save redirects back to the form with an `error` message, which the form shows.

## Renderer and model

`internal.services.email_renderer.EmailRenderer` compiles MJML with `mrml`, extracts the
`%variable%` placeholders of a template, derives a plain-text version with BeautifulSoup,
substitutes variables and validates MJML. The route handlers currently delegate compilation
and rendering to the mailler service, so the renderer is not wired into a page yet; it is
covered by its own tests and kept for local rendering.

## Data model

`EmailTemplate` describes the mailler service's template table; the pages do not query it
directly (they use the mailler API), but the campaign models reference it.

**`EmailTemplate`** maps the `email_templates` table: `id`, `slug`, `name`, `description`, `subject_template`, `mjml_source`, `html_compiled`, `plain_text`, `status`, `variables`, `metadata_`, `created_at`, `updated_at`.

`EmailTemplateStatus` is a string enum (`draft`, `active`, `archived`). No migrations are shipped.

## Tests

pytest:

- `tests/routes/test_email_templates.py`
- `tests/services/test_email_renderer.py`
- `tests/routes/test_email_templates_sidebar.py`

The tests cover each route handler (including the compile endpoint's error branches) and the renderer (compilation, variable extraction, plain-text conversion, rendering, validation).

`tests/routes/test_email_templates_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/email_templates.feature`):

- List email templates
- List email templates unauthenticated
- List email templates with search filter
- List email templates with status filter
- View new template form
- Create a new template successfully
- Create a new template failure
- Create a template with auto-generated slug
- View template detail
- View template detail not found
- View template edit form
- Update a template successfully
- Update a template failure
- Compile MJML successfully
- Compile MJML with errors
- Compile MJML with empty source
- Preview template with sample data
- Preview template not found
- Duplicate a template successfully
- Duplicate a template not found
- Delete a template successfully
- Delete a template failure
- Bulk delete templates
- Bulk delete with no selection
- Sidebar on the email templates list
- Sidebar on the new email template form
- Sidebar on the email template detail
- Sidebar on the email template edit form
- Sidebar gated links follow the scopes on the email templates list

The mailler client is replaced by an `AsyncMock`; scenarios cover listing, filters, create, edit, preview, compile, duplicate, deletion and unauthorized access.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/email_templates.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The templates are listed
- The Email Templates link leads to the list
- A user without the template scope gets the access denied page
- An anonymous visitor comes back to the page asked for after the login
- The templates are filtered by status
- The search is kept in the address
- A template is created from the visual editor
- The slug is derived from the name
- A template can be written as MJML code
- MJML without its root tag is stopped before it is sent
- The live preview reports a compilation error
- The form requires a name and a subject
- A template the mailler service refuses is reported on the form
- The list leads to the detail of a template
- A template that does not exist sends the user back to the list
- A template is updated from its edit form
- A template the mailler service cannot update is reported on the form
- A template is duplicated and its copy is opened for editing
- A template is deleted from its page after a confirmation
- A template is deleted from its edit form after a confirmation
- A template the mailler service cannot delete is reported
- Selected templates are deleted in bulk

The visual editor and the MJML code view build the source the form sends, the live preview compiles it through the mocked mailler service, and a source without its `<mjml>` root is stopped by an alert before it is sent.
