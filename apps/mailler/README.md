# Mailler

Internal email sending service.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring |
| POST | `/api/v1/send` | scope `mailler:send` | Send an email immediately (async via Celery) |
| POST | `/api/v1/schedule` | scope `mailler:send` | Schedule an email for future delivery |
| GET | `/api/v1/emails` | scope `mailler:read` | List the emails of the calling client with pagination |
| GET | `/api/v1/emails/{email_id}` | scope `mailler:read` | Get email details by ID |
| GET | `/api/v1/stats` | scope `mailler:stats` | Get the email sending statistics of the calling client (real-time from emails table) |
| GET | `/api/v1/providers` | scope `mailler:read` | List available (configured) email providers |
| GET | `/api/v1/templates` | scope `mailler:read` | List the email templates of the calling client with pagination |
| POST | `/api/v1/templates` | scope `mailler:write` | Create a new email template |
| GET | `/api/v1/templates/{template_id}` | scope `mailler:read` | Get email template by ID |
| GET | `/api/v1/templates/by-slug/{slug}` | scope `mailler:read` | Get an email template of the calling client by slug |
| PUT | `/api/v1/templates/{template_id}` | scope `mailler:write` | Update an email template |
| DELETE | `/api/v1/templates/{template_id}` | scope `mailler:write` | Delete an email template |
| POST | `/api/v1/templates/compile` | scope `mailler:read` | Compile MJML to HTML without saving |
| POST | `/api/v1/templates/{template_id}/render` | scope `mailler:read` | Render a template with provided variables |
| GET | `/api/v1/contacts` | scope `mailler:read` | List the contacts of the calling client with pagination |
| POST | `/api/v1/contacts` | scope `mailler:write` | Create a new contact |
| POST | `/api/v1/contacts/bulk` | scope `mailler:write` | Create multiple contacts at once |
| GET | `/api/v1/contacts/{contact_id}` | scope `mailler:read` | Get contact by ID |
| GET | `/api/v1/contacts/by-email/{email}` | scope `mailler:read` | Get a contact of the calling client by email address |
| PUT | `/api/v1/contacts/{contact_id}` | scope `mailler:write` | Update a contact |
| DELETE | `/api/v1/contacts/{contact_id}` | scope `mailler:write` | Delete a contact |
| POST | `/api/v1/contacts/{contact_id}/unsubscribe` | scope `mailler:write` | Unsubscribe a contact from all emails |
| GET | `/api/v1/contact-groups` | scope `mailler:read` | List the contact groups of the calling client with pagination |
| POST | `/api/v1/contact-groups` | scope `mailler:write` | Create a new contact group |
| GET | `/api/v1/contact-groups/{group_id}` | scope `mailler:read` | Get contact group by ID |
| GET | `/api/v1/contact-groups/by-slug/{slug}` | scope `mailler:read` | Get a contact group of the calling client by slug |
| PUT | `/api/v1/contact-groups/{group_id}` | scope `mailler:write` | Update a contact group |
| DELETE | `/api/v1/contact-groups/{group_id}` | scope `mailler:write` | Delete a contact group |
| GET | `/api/v1/contact-groups/{group_id}/contacts` | scope `mailler:read` | List contacts in a group with pagination |
| GET | `/api/v1/contact-groups/{group_id}/available-contacts` | scope `mailler:read` | List contacts NOT in a group (available for adding) |
| POST | `/api/v1/contact-groups/{group_id}/contacts` | scope `mailler:write` | Add contacts to a group |
| DELETE | `/api/v1/contact-groups/{group_id}/contacts` | scope `mailler:write` | Remove contacts from a group |
| GET | `/api/v1/campaigns` | scope `mailler:read` | List the campaigns of the calling client with pagination |
| POST | `/api/v1/campaigns` | scope `mailler:write` | Create a new campaign |
| GET | `/api/v1/campaigns/{campaign_id}` | scope `mailler:read` | Get campaign by ID |
| PUT | `/api/v1/campaigns/{campaign_id}` | scope `mailler:write` | Update a campaign |
| DELETE | `/api/v1/campaigns/{campaign_id}` | scope `mailler:write` | Delete a campaign |
| POST | `/api/v1/campaigns/{campaign_id}/schedule` | scope `mailler:send` | Schedule a campaign for future sending |
| POST | `/api/v1/campaigns/{campaign_id}/send` | scope `mailler:send` | Start sending a campaign immediately |
| POST | `/api/v1/campaigns/{campaign_id}/pause` | scope `mailler:send` | Pause a sending campaign |
| POST | `/api/v1/campaigns/{campaign_id}/resume` | scope `mailler:send` | Resume a paused campaign |
| GET | `/api/v1/campaigns/{campaign_id}/preview` | scope `mailler:read` | Preview a campaign with sample data |
| GET | `/api/v1/campaigns/{campaign_id}/sends` | scope `mailler:read` | List sends for a campaign |
| GET | `/api/v1/unsubscribe` | public; HMAC-signed link | Display unsubscribe confirmation page |
| POST | `/api/v1/unsubscribe` | public; HMAC-signed link | Process unsubscribe request |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

Emails, templates, contacts, groups and campaigns belong to the client of the access token (`client_id`): a caller sees and acts only on its own client, and only a holder of the `ADMIN_SCOPE` setting scope can name another one.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `mailler:send` - checked by 6 routes
- `mailler:read` - checked by 20 routes
- `mailler:stats` - checked by 1 route
- `mailler:write` - checked by 16 routes
