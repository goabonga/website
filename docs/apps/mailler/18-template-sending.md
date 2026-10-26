# Sending from a template

`POST /api/v1/send` and `POST /api/v1/schedule` accept the slug of one of the
templates of the client instead of the content of the email. The service
renders the subject, the HTML and the plain text from the variables of the
request, so an application sends a transactional email (an invitation, a
notification) in a single call, without reading the template and rendering it
itself. The provider is optional too: it comes from the
[client record](15-authorized-clients.md).

Mailler contains no template of any application. Each client uploads its own
through the [template API](08-templates.md) or imports a whole set with the
[command line](17-command-line.md).

## Request

Instead of `subject` and `html_content` (and `text_content`) the body carries:

| Field | Required | Description |
| --- | --- | --- |
| `template_slug` | yes | Slug of an `active` template of the caller's client (lowercase letters, digits, hyphens and underscores, for example `workspace_invitation`) |
| `variables` | no | JSON object of the values used by the template |

The other fields (`to_email`, `to_name`, `from_email`, `from_name`, `reply_to`,
`provider`, `metadata`, and `scheduled_at` for `/schedule`) are the ones of the
[send](04-send.md) request and follow the same rules for the sender and the
provider. A body must carry either `template_slug` or the content: giving both
(or `variables` without a template, or neither) is refused with `422`.

```json
{
  "to_email": "newcomer@example.com",
  "template_slug": "workspace_invitation",
  "variables": {"inviter": "Ann", "workspace": "Acme", "link": "https://app.example/join/42"}
}
```

## Rendering

- The template is looked up among the templates of the caller's client, so a
  client can only send its own and the same slug can exist for several clients.
  An unknown slug gives `404`; a template that is not `active` or not
  compiled gives `422`.
- The HTML is the compiled MJML rendered with Jinja2 in the sandbox of the
  [templates](08-templates.md) feature, with auto-escaping on: a value such
  as `<b>` or `&` cannot inject markup. The subject and the plain text are
  rendered without escaping.
- The plain text is the `plain_text` of the template (where `%name%` stands
  for `{{ name }}`) or, when the template has none, a text version derived from
  the rendered HTML.
- A rendering error (syntax error, failing expression, forbidden construct, an
  empty subject or one longer than 500 characters) gives `422` and nothing is
  stored.
- A variable the request does not provide renders as an empty string. The
  names of the variables of the template that the request left out are listed
  in `missing_variables` of the response, so a caller can notice a forgotten
  value; the email is sent anyway.
- The stored email is an ordinary email: `GET /emails/{id}` returns the
  rendered content, and `metadata.template_slug` records the template used.

The response is the one of `/send` and `/schedule` plus `missing_variables`
(an empty list when nothing is missing).

## How it is tested

- pytest: `tests/test_schemas_email.py` (one of template or content),
  `tests/test_services_template_content.py` (lookup, status, rendering,
  escaping, errors, missing variables), and the template cases of the send and
  schedule route tests.
- behave: `features/template_sending.feature` imports templates with the
  command line, then sends them: one call with escaping and the derived or
  explicit plain text, missing variables, scheduling, unknown and foreign
  templates, drafts, conflicting bodies, the sender rules, a hostile template
  and the scope. The MJML compiler runs for real.
