# internal

Internal admin dashboard for managing platform services.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. `session` routes need a signed-in user and redirect to the login page otherwise. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint (hidden from Swagger) |
| GET | `/auth/login` | public | Redirect to OAuth2 authorization endpoint |
| GET | `/auth/callback` | public | OAuth2 callback - exchange authorization code for tokens |
| GET | `/auth/logout` | public | Logout - clear authentication cookies |
| GET | `/auth/refresh` | refresh token cookie | Refresh access token using refresh token |
| GET | `/` | session; scope `conversations:read` | Admin dashboard with chat statistics |
| GET | `/conversations` | session; scope `conversations:read` | List all conversations with pagination and search |
| GET | `/conversations/{conversation_id}` | session; scope `conversations:read` | View conversation detail with all messages |
| POST | `/conversations/{conversation_id}/delete` | session; scope `conversations:delete` | Delete a conversation and all its messages |
| POST | `/conversations/bulk-delete` | session; scope `conversations:delete` | Delete multiple conversations and all their messages |
| GET | `/analytics` | session; scope `analytics:read` | Analytics overview dashboard |
| GET | `/analytics/campaigns` | session; scope `analytics:read` | List all marketing campaigns |
| GET | `/analytics/campaigns/{campaign_id}` | session; scope `analytics:read` | View detailed campaign statistics |
| POST | `/analytics/campaigns/{campaign_id}/delete` | session; scope `analytics:write` | Delete an analytics campaign |
| POST | `/analytics/campaigns/bulk-delete` | session; scope `analytics:write` | Delete multiple analytics campaigns |
| GET | `/analytics/ips` | session; scope `analytics:read` | List IP addresses with their statistics |
| GET | `/analytics/ips/{ip_address:path}` | session; scope `analytics:read` | View detailed statistics for a specific IP address |
| POST | `/analytics/reset` | session; scope `analytics:delete` | Reset all analytics data |
| GET | `/contacts` | session; scope `contacts:read` | List all contacts with pagination, search, and filtering |
| GET | `/contacts/new` | session; scope `contacts:write` | Show form to create a new contact |
| POST | `/contacts/new` | session; scope `contacts:write` | Create a new contact |
| GET | `/contacts/import` | session; scope `contacts:write` | Show CSV import form |
| POST | `/contacts/import` | session; scope `contacts:write` | Import contacts from CSV file |
| GET | `/contacts/export` | session; scope `contacts:read` | Export contacts to CSV file |
| GET | `/contacts/{contact_id}` | session; scope `contacts:read` | View contact detail |
| GET | `/contacts/{contact_id}/edit` | session; scope `contacts:write` | Show form to edit a contact |
| POST | `/contacts/{contact_id}/edit` | session; scope `contacts:write` | Update a contact |
| POST | `/contacts/{contact_id}/unsubscribe` | session; scope `contacts:write` | Mark a contact as unsubscribed |
| POST | `/contacts/{contact_id}/delete` | session; scope `contacts:delete` | Delete a contact |
| POST | `/contacts/bulk-delete` | session; scope `contacts:delete` | Delete multiple contacts |
| POST | `/contacts/bulk-add-to-group` | session; scope `contacts:write` | Add multiple contacts to a group |
| GET | `/contact-groups` | session; scope `contacts:read` | List all contact groups with pagination |
| GET | `/contact-groups/new` | session; scope `contacts:write` | Show form to create a new contact group |
| POST | `/contact-groups/new` | session; scope `contacts:write` | Create a new contact group |
| GET | `/contact-groups/{group_id}` | session; scope `contacts:read` | View contact group detail with member list |
| GET | `/contact-groups/{group_id}/edit` | session; scope `contacts:write` | Show form to edit a contact group |
| POST | `/contact-groups/{group_id}/edit` | session; scope `contacts:write` | Update a contact group |
| GET | `/contact-groups/{group_id}/add-contacts` | session; scope `contacts:write` | Show form to add contacts to a group |
| POST | `/contact-groups/{group_id}/add-contacts` | session; scope `contacts:write` | Add contacts to a group |
| POST | `/contact-groups/{group_id}/remove-contacts` | session; scope `contacts:write` | Remove contacts from a group |
| POST | `/contact-groups/bulk-delete` | session; scope `contacts:delete` | Delete multiple contact groups |
| POST | `/contact-groups/{group_id}/delete` | session; scope `contacts:delete` | Delete a contact group |
| GET | `/email-campaigns` | session; scope `email_campaigns:read` | List all email campaigns with pagination and filtering |
| GET | `/email-campaigns/new` | session; scope `email_campaigns:write` | Show form to create a new email campaign |
| POST | `/email-campaigns/new` | session; scope `email_campaigns:write` | Create a new email campaign |
| POST | `/email-campaigns/bulk-delete` | session; scope `email_campaigns:delete` | Delete multiple email campaigns at once |
| GET | `/email-campaigns/{campaign_id}` | session; scope `email_campaigns:read` | View email campaign detail with statistics |
| GET | `/email-campaigns/{campaign_id}/edit` | session; scope `email_campaigns:write` | Show form to edit an email campaign |
| POST | `/email-campaigns/{campaign_id}/edit` | session; scope `email_campaigns:write` | Update an email campaign |
| POST | `/email-campaigns/{campaign_id}/send` | session; scope `email_campaigns:send` | Start sending an email campaign |
| POST | `/email-campaigns/{campaign_id}/pause` | session; scope `email_campaigns:send` | Pause a sending campaign |
| POST | `/email-campaigns/{campaign_id}/resume` | session; scope `email_campaigns:send` | Resume a paused campaign |
| POST | `/email-campaigns/{campaign_id}/delete` | session; scope `email_campaigns:delete` | Delete an email campaign |
| GET | `/email-campaigns/{campaign_id}/stats` | session; scope `email_campaigns:read` | Get campaign statistics as JSON (for AJAX updates) |
| GET | `/email-templates` | session; scope `email_templates:read` | List all email templates with pagination and filtering |
| GET | `/email-templates/new` | session; scope `email_templates:write` | Show form to create a new email template |
| POST | `/email-templates/new` | session; scope `email_templates:write` | Create a new email template |
| GET | `/email-templates/{template_id}` | session; scope `email_templates:read` | View email template detail with preview |
| GET | `/email-templates/{template_id}/edit` | session; scope `email_templates:write` | Show form to edit an email template |
| POST | `/email-templates/{template_id}/edit` | session; scope `email_templates:write` | Update an email template |
| POST | `/email-templates/compile` | session; scope `email_templates:read` | AJAX endpoint to compile MJML and return HTML preview |
| POST | `/email-templates/{template_id}/preview` | session; scope `email_templates:read` | Preview email template with sample data |
| POST | `/email-templates/{template_id}/duplicate` | session; scope `email_templates:write` | Duplicate an email template |
| POST | `/email-templates/bulk-delete` | session; scope `email_templates:delete` | Delete multiple email templates |
| POST | `/email-templates/{template_id}/delete` | session; scope `email_templates:delete` | Delete an email template |
| GET | `/knowledge` | session; scope `knowledge:read` | List all knowledge entries with pagination, search, namespace and status filter |
| GET | `/knowledge/new` | session; scope `knowledge:write` | Show form to create a new knowledge entry |
| GET | `/knowledge/generate` | session; scope `knowledge:write` | Show form to generate knowledge entries using AI |
| POST | `/knowledge/generate` | session; scope `knowledge:write` | Dispatch async knowledge generation task |
| GET | `/knowledge/generate/status/{task_id}` | session; scope `knowledge:read` | Poll generation task status |
| POST | `/knowledge/new` | session; scope `knowledge:write` | Create a new knowledge entry with embedding |
| GET | `/knowledge/{entry_id}` | session; scope `knowledge:read` | View knowledge entry detail |
| GET | `/knowledge/{entry_id}/edit` | session; scope `knowledge:write` | Show form to edit a knowledge entry |
| POST | `/knowledge/{entry_id}/edit` | session; scope `knowledge:write` | Update a knowledge entry with new embedding if question changed |
| POST | `/knowledge/{entry_id}/regenerate-embedding` | session; scope `knowledge:write` | Regenerate embedding for an existing entry |
| GET | `/knowledge/{entry_id}/validation` | session; scope `knowledge:read` | View validation details for a knowledge entry |
| POST | `/knowledge/{entry_id}/revalidate` | session; scope `knowledge:write` | Re-trigger validation for an entry |
| POST | `/knowledge/{entry_id}/approve` | session; scope `knowledge:write` | Manually approve a NEEDS_REVIEW or REJECTED entry |
| POST | `/knowledge/{entry_id}/reject` | session; scope `knowledge:write` | Manually reject an entry |
| POST | `/knowledge/{entry_id}/delete` | session; scope `knowledge:delete` | Delete a knowledge entry |
| POST | `/knowledge/bulk-delete` | session; scope `knowledge:delete` | Delete multiple knowledge entries |
| GET | `/mailler` | session; scope `mailler:read` | Mailler statistics dashboard |
| GET | `/mailler/emails` | session; scope `mailler:read` | List all emails with pagination and filters |
| GET | `/mailler/emails/{email_id}` | session; scope `mailler:read` | View email details |
| GET | `/mailler/clients` | session; scope `mailler:admin` | List the clients authorized to use the mailler service |
| GET | `/mailler/clients/new` | session; scope `mailler:admin` | Form to register a client |
| POST | `/mailler/clients/new` | session; scope `mailler:admin` | Register a client |
| GET | `/mailler/clients/{client_id}/edit` | session; scope `mailler:admin` | Form to edit a client |
| POST | `/mailler/clients/{client_id}/edit` | session; scope `mailler:admin` | Update a client: every field of the form is applied, an empty one removes the value |
| POST | `/mailler/clients/{client_id}/deactivate` | session; scope `mailler:admin` | Deactivate a client: the mailler service refuses it from then on and stops its work |
| POST | `/mailler/clients/{client_id}/activate` | session; scope `mailler:admin` | Activate a client again |
| GET | `/namespaces` | session; scope `namespaces:read` | List all namespaces with pagination and search |
| GET | `/namespaces/new` | session; scope `namespaces:write` | Show form to create a new namespace |
| POST | `/namespaces/new` | session; scope `namespaces:write` | Create a new namespace |
| GET | `/namespaces/{namespace_id}` | session; scope `namespaces:read` | View namespace detail |
| GET | `/namespaces/{namespace_id}/edit` | session; scope `namespaces:write` | Show form to edit a namespace |
| POST | `/namespaces/{namespace_id}/edit` | session; scope `namespaces:write` | Update a namespace |
| POST | `/namespaces/bulk-delete` | session; scope `namespaces:delete` | Delete multiple namespaces |
| POST | `/namespaces/{namespace_id}/delete` | session; scope `namespaces:delete` | Delete a namespace |
| GET | `/prompts/generate` | session; scope `prompts:write` | Show form to generate a prompt using AI |
| POST | `/prompts/generate` | session; scope `prompts:write` | Generate a prompt using AI from description |
| GET | `/prompts` | session; scope `prompts:read` | List all prompts with pagination and search |
| GET | `/prompts/new` | session; scope `prompts:write` | Show form to create a new prompt |
| POST | `/prompts/new` | session; scope `prompts:write` | Create a new prompt with initial version |
| GET | `/prompts/{prompt_id}` | session; scope `prompts:read` | View prompt detail with version history |
| GET | `/prompts/{prompt_id}/edit` | session; scope `prompts:write` | Show form to edit a prompt (creates new version) |
| POST | `/prompts/{prompt_id}/edit` | session; scope `prompts:write` | Update a prompt (creates new version if content changed) |
| POST | `/prompts/{prompt_id}/version/{version_id}/activate` | session; scope `prompts:write` | Activate a specific version of a prompt |
| POST | `/prompts/{prompt_id}/version/{version_id}/delete` | session; scope `prompts:delete` | Delete a specific version of a prompt |
| POST | `/prompts/{prompt_id}/versions/bulk-delete` | session; scope `prompts:delete` | Delete multiple versions of a prompt |
| POST | `/prompts/bulk-delete` | session; scope `prompts:delete` | Delete multiple prompts |
| POST | `/prompts/{prompt_id}/delete` | session; scope `prompts:delete` | Delete a prompt |
| GET | `/team` | session; scope `team:read` | Team dashboard - overview of all teams |
| GET | `/team/new` | session; scope `team:write` | New team form |
| POST | `/team/new` | session; scope `team:write` | Create a new team |
| GET | `/team/{team_id}` | session; scope `team:read` | Team detail view with agents, workflows, conversations |
| GET | `/team/{team_id}/edit` | session; scope `team:write` | Edit team form |
| POST | `/team/{team_id}/edit` | session; scope `team:write` | Update a team |
| POST | `/team/{team_id}/delete` | session; scope `team:write` | Delete a team |
| GET | `/team/{team_id}/agents` | session; scope `team:read` | List agents for a team |
| GET | `/team/{team_id}/agents/new` | session; scope `team:write` | New agent form |
| POST | `/team/{team_id}/agents/new` | session; scope `team:write` | Create a new agent |
| GET | `/team/{team_id}/agents/{agent_id}` | session; scope `team:read` | Agent detail view |
| GET | `/team/{team_id}/agents/{agent_id}/edit` | session; scope `team:write` | Edit agent form |
| POST | `/team/{team_id}/agents/{agent_id}/edit` | session; scope `team:write` | Update an agent |
| POST | `/team/{team_id}/agents/{agent_id}/delete` | session; scope `team:write` | Delete an agent |
| POST | `/team/{team_id}/agents/{agent_id}/skills/new` | session; scope `team:write` | Create a new skill for an agent |
| POST | `/team/{team_id}/agents/{agent_id}/skills/{skill_id}/delete` | session; scope `team:write` | Delete a skill |
| GET | `/team/{team_id}/agents/{agent_id}/skills/{skill_id}/edit` | session; scope `team:write` | Edit skill form |
| POST | `/team/{team_id}/agents/{agent_id}/skills/{skill_id}/edit` | session; scope `team:write` | Update a skill |
| GET | `/team/{team_id}/workflows` | session; scope `team:read` | List workflows for a team |
| GET | `/team/{team_id}/workflows/new` | session; scope `team:write` | New workflow form |
| POST | `/team/{team_id}/workflows/new` | session; scope `team:write` | Create a new workflow |
| GET | `/team/{team_id}/workflows/{workflow_id}/edit` | session; scope `team:write` | Edit workflow form |
| POST | `/team/{team_id}/workflows/{workflow_id}/edit` | session; scope `team:write` | Update a workflow |
| POST | `/team/{team_id}/workflows/{workflow_id}/delete` | session; scope `team:write` | Delete a workflow |
| GET | `/team/{team_id}/run` | session; scope `team:write` | Show the form to launch an agent conversation |
| POST | `/team/{team_id}/run` | session; scope `team:write` | Create a task and trigger agent execution |
| GET | `/team/{team_id}/conversations` | session; scope `team:read` | List conversations |
| GET | `/team/{team_id}/conversations/{conv_id}` | session; scope `team:read` | Conversation detail with messages |
| GET | `/team/{team_id}/conversations/{conv_id}/status` | session; scope `team:read` | Get conversation status and message count as JSON (for polling) |
| POST | `/team/{team_id}/conversations/{conv_id}/delete` | session; scope `team:write` | Delete a conversation |
| POST | `/team/{team_id}/conversations/bulk-delete` | session; scope `team:write` | Bulk delete conversations |
| POST | `/team/{team_id}/conversations/{conv_id}/cancel-task` | session; scope `team:write` | Cancel the task linked to a conversation |
| POST | `/team/{team_id}/conversations/bulk-cancel` | session; scope `team:write` | Bulk cancel tasks linked to conversations |
| GET | `/team/{team_id}/memory` | session; scope `team:read` | List memory entries for a team |
| POST | `/team/{team_id}/memory/{memory_id}/delete` | session; scope `team:write` | Delete a single memory entry |
| POST | `/team/{team_id}/memory/bulk-delete` | session; scope `team:write` | Bulk delete memory entries |
| GET | `/vpn/sessions` | session; scope `vpn:admin` | List all VPN sessions with pagination |
| POST | `/vpn/sessions/{serial_number}/revoke` | session; scope `vpn:admin` | Revoke a VPN session by certificate serial number |
| GET | `/billing` | session; scope `billing:read` | Billing dashboard - overview of all SaaS apps |
| GET | `/billing/saas/new` | session; scope `billing:write` | New SaaS app form |
| POST | `/billing/saas/new` | session; scope `billing:write` | Create a new SaaS app |
| GET | `/billing/saas/{saas_id}` | session; scope `billing:read` | SaaS app detail view with products and customers |
| POST | `/billing/saas/{saas_id}/clients` | session; scope `billing:admin` | Bind an OAuth client to a SaaS app: it may then act on that app's data |
| POST | `/billing/saas/{saas_id}/clients/unbind` | session; scope `billing:admin` | Remove the binding of an OAuth client to a SaaS app |
| GET | `/billing/saas/{saas_id}/edit` | session; scope `billing:write` | Edit SaaS app form |
| POST | `/billing/saas/{saas_id}/edit` | session; scope `billing:write` | Update a SaaS app (an unchecked "Active" box is not submitted: it deactivates) |
| GET | `/billing/saas/{saas_id}/products` | session; scope `billing:read` | List all products for a SaaS app |
| GET | `/billing/saas/{saas_id}/products/new` | session; scope `billing:write` | New product form |
| POST | `/billing/saas/{saas_id}/products/new` | session; scope `billing:write` | Create a new product in Stripe with features, limits, and trial settings |
| GET | `/billing/saas/{saas_id}/products/{product_id}` | session; scope `billing:read` | Product detail with prices |
| GET | `/billing/saas/{saas_id}/products/{product_id}/edit` | session; scope `billing:write` | Edit product form with features and limits |
| POST | `/billing/saas/{saas_id}/products/{product_id}/edit` | session; scope `billing:write` | Update a product with features, limits, and trial settings |
| GET | `/billing/saas/{saas_id}/products/{product_id}/prices/new` | session; scope `billing:write` | New price form |
| POST | `/billing/saas/{saas_id}/products/{product_id}/prices/new` | session; scope `billing:write` | Create a new price in Stripe |
| POST | `/billing/saas/{saas_id}/products/{product_id}/prices/{price_id}/toggle` | session; scope `billing:write` | Toggle a price active/inactive status |
| GET | `/billing/saas/{saas_id}/customers` | session; scope `billing:read` | List customers for a SaaS app |
| GET | `/billing/saas/{saas_id}/customers/{customer_id}` | session; scope `billing:read` | Customer detail with subscriptions |
| POST | `/billing/saas/{saas_id}/customers/{customer_id}/portal` | session; scope `billing:read` | Redirect to Stripe Customer Portal |
| GET | `/billing/saas/{saas_id}/subscriptions` | session; scope `billing:read` | List subscriptions for a SaaS app |
| GET | `/billing/saas/{saas_id}/subscriptions/{subscription_id}` | session; scope `billing:read` | Subscription detail view |
| POST | `/billing/saas/{saas_id}/subscriptions/{subscription_id}/cancel` | session; scope `billing:write` | Cancel a subscription |
| POST | `/billing/saas/{saas_id}/subscriptions/{subscription_id}/reactivate` | session; scope `billing:write` | Undo a cancellation scheduled for the end of the period |
| POST | `/billing/saas/{saas_id}/subscriptions/{subscription_id}/sync` | session; scope `billing:write` | Sync a subscription from Stripe |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `conversations:read` - checked by 3 routes
- `conversations:delete` - checked by 2 routes
- `analytics:read` - checked by 5 routes
- `analytics:write` - checked by 2 routes
- `analytics:delete` - checked by 1 route
- `contacts:read` - checked by 5 routes
- `contacts:write` - checked by 15 routes
- `contacts:delete` - checked by 4 routes
- `email_campaigns:read` - checked by 3 routes
- `email_campaigns:write` - checked by 4 routes
- `email_campaigns:delete` - checked by 2 routes
- `email_campaigns:send` - checked by 3 routes
- `email_templates:read` - checked by 4 routes
- `email_templates:write` - checked by 5 routes
- `email_templates:delete` - checked by 2 routes
- `knowledge:read` - checked by 4 routes
- `knowledge:write` - checked by 10 routes
- `knowledge:delete` - checked by 2 routes
- `mailler:read` - checked by 3 routes
- `mailler:admin` - checked by 7 routes
- `namespaces:read` - checked by 2 routes
- `namespaces:write` - checked by 4 routes
- `namespaces:delete` - checked by 2 routes
- `prompts:write` - checked by 7 routes
- `prompts:read` - checked by 2 routes
- `prompts:delete` - checked by 4 routes
- `team:read` - checked by 9 routes
- `team:write` - checked by 27 routes
- `vpn:admin` - checked by 2 routes
- `billing:read` - checked by 9 routes
- `billing:write` - checked by 14 routes
- `billing:admin` - checked by 2 routes
