# Onboarding a SaaS application

Three services of the platform are shared by several applications ("clients"):
`custom_domain` (customer domain names), `mailler` (transactional email) and
`billing` (Stripe subscriptions). Each one keeps a registry of the OAuth clients
allowed to use it and isolates their data. A service that has just been deployed
refuses every client until it is registered, so onboarding an application is
part of the deployment. This page lists what to declare in the inventory and
what to create elsewhere; the variables are described in
[python_app](roles/python_app.md).

Nothing here is specific to one application: no identifier, quota, sender,
domain or URL is built into the collection or the services, they all come from
the inventory.

## 1. The OAuth client, at the authentication server

Each application authenticates with its own OAuth client (client credentials)
and sends the bearer token to the services. The services identify it by the
`client_id` (or `azp`) of the token, so **every OAuth client an application sends
with must be registered**: its web client and its backend client are two
different clients for a service.

Create the client at the authentication server and give it the scopes it needs.
The collection does not create it; it only needs its identifier for the
applications that validate tokens (`website_oauth2_clients`).

| Service | Scopes for an application | Operator only |
| --- | --- | --- |
| `custom_domain` | `custom-domain:read`, `custom-domain:write`, and `custom-domain:lookup` to resolve a host name to its owner | `custom-domain:admin` crosses client boundaries: never give it to an application |
| `mailler` | `mailler:send`, `mailler:read`, `mailler:write` (upload templates, manage contacts and campaigns), `mailler:stats` | `mailler:admin` (`ADMIN_SCOPE`): see and manage every client |
| `billing` | `billing:platform:read`, `billing:platform:write`, `billing:checkout:write`, `billing:usage:write`, as the application needs | `billing:admin` (`website_billing_partition_admin_scope`): act on every SaaS application and manage the bindings |

The scopes of `custom_domain`, `billing` and `mailler:send`/`read`/`stats` are
created by the migrations of the authentication server; `mailler:write` and
`mailler:admin` are not, and must be created there before they can be granted.
The operator client of the `internal` application needs the platform scopes and
the admin scopes of billing and mailler (see
[python_app](roles/python_app.md#internal)).

## 2. Declare the application in the inventory

```yaml
# group_vars/all/onboarding.yml
website_custom_domain_clients:
  - client_id: "{{ vault_my_app_oauth2_client_id }}"
    name: My application
    upstream: /run/my-app/my-app.sock       # socket path or host:port
    cname: apps.example.invalid             # what the customers point their CNAME at
    max_domains: 100
    webhook_url: https://my-app.example.invalid/hooks/custom-domain
    webhook_secret: "{{ vault_my_app_custom_domain_webhook_secret }}"   # 32 characters or more

website_mailler_clients:
  - client_id: "{{ vault_my_app_oauth2_client_id }}"
    name: My application
    from_email: no-reply@my-app.example.invalid
    from_name: My application
    allowed_providers: [brevo]
    default_provider: brevo
    daily_quota: 5000
    rate_limit_per_minute: 60
    callback_url: https://my-app.example.invalid/hooks/mailler
    callback_secret: "{{ vault_my_app_mailler_callback_secret }}"

website_mailler_template_dirs:
  - client_id: "{{ vault_my_app_oauth2_client_id }}"
    directory: /opt/my-app/current/apps/my-app/templates/mailler   # <slug>.mjml + <slug>.json

website_billing_saas_apps:
  - slug: my-app
    name: My application
    webhook_url: https://my-app.example.invalid/hooks/billing
    checkout_urls: [https://my-app.example.invalid/]

website_billing_client_bindings:
  - saas: my-app
    client_id: "{{ vault_my_app_oauth2_client_id }}"
```

Declare only the services the application uses. The names above are
placeholders: the providers must be configured on the service (an API key, a
region, a host), and the sender must be one the provider accepts.

Then deploy the services; the registration runs after the migrations of each
service, in this order: `custom_domain`, `mailler`, `billing` (the order of
`website_apps_enabled`):

```bash
ansible-playbook goabonga.website.apps -i inventory/hosts \
    -e '{"website_apps_limit": ["custom_domain", "mailler", "billing"]}'
```

## Example: knowledge

`knowledge` is a client of the three services. With its OAuth client
(`website_oauth2_clients.knowledge.client_id`, the scopes of the table above:
`mailler:send`; `custom-domain:read` and `custom-domain:write`;
`billing:platform:read`, `billing:platform:write` and `billing:checkout:write`;
no admin scope) the inventory holds:

```yaml
website_mailler_clients:
  - client_id: "{{ website_oauth2_clients.knowledge.client_id }}"
    name: Knowledge
    from_email: no-reply@knowledge.example.invalid
    from_name: Knowledge
    allowed_providers: [brevo]
    default_provider: brevo
    daily_quota: 5000
    rate_limit_per_minute: 60

website_mailler_template_dirs:
  - client_id: "{{ website_oauth2_clients.knowledge.client_id }}"
    app: knowledge                       # deployed before mailler
    module: knowledge.email_templates    # prints the directory of the templates

website_custom_domain_clients:
  - client_id: "{{ website_oauth2_clients.knowledge.client_id }}"
    name: Knowledge
    upstream: /run/knowledge/knowledge.sock
    cname: apps.example.invalid
    max_domains: 100
    webhook_url: https://knowledge.example.invalid/webhooks/custom-domain
    webhook_secret: "{{ vault_knowledge_custom_domain_webhook_secret }}"

website_billing_saas_apps:
  - slug: knowledge
    name: Knowledge
    checkout_urls: [https://knowledge.example.invalid/]
    webhook_url: https://knowledge.example.invalid/webhooks/billing

website_billing_client_bindings:
  - saas: knowledge
    client_id: "{{ website_oauth2_clients.knowledge.client_id }}"

website_secrets:
  knowledge:
    OPENAI_API_KEY: "{{ vault_openai_api_key }}"
    OAUTH2_CLIENT_SECRET: "{{ vault_knowledge_oauth2_client_secret }}"
    CUSTOM_DOMAIN_WEBHOOK_SECRET: "{{ vault_knowledge_custom_domain_webhook_secret }}"   # same as the client above
    BILLING_WEBHOOK_SECRET: "{{ vault_knowledge_billing_webhook_secret }}"

website_knowledge_billing_app_slug: knowledge
website_knowledge_billing_saas_id: "{{ vault_knowledge_billing_saas_id }}"   # from `billing-admin saas list`
website_knowledge_billing_checkout_success_url: https://knowledge.example.invalid/checkout/success
website_knowledge_billing_checkout_cancel_url: https://knowledge.example.invalid/checkout/cancel
```

What the other services need from the deployment of knowledge:

- Enable `knowledge` before `mailler` in `website_apps_enabled` the first time:
  the templates are imported with the Python of the knowledge virtualenv.
- The status webhooks come back to `/webhooks/billing` and
  `/webhooks/custom-domain` of the public host name; both stay reachable (POST
  only) even when the host is restricted with `nginx.allowed_hosts`.
- The custom-domain service writes the virtual host of each customer domain
  and proxies it to the `upstream` socket: nginx can open it because the role
  adds its user to the group of knowledge.
- `billing-admin` cannot store the secret that signs the billing webhook: set
  the `webhook_secret` of the SaaS application in the internal interface or with
  `PATCH /platform/saas/<id>`, to the value of `BILLING_WEBHOOK_SECRET`. The
  identifier of the application, which the first run discovers
  (`billing-admin saas list`), goes in `website_knowledge_billing_saas_id` for the
  second run: until then knowledge does not use billing.
- The products of the plans (slugs `free`, `starter`, `pro`, `enterprise`, with
  their limits and prices) are created in billing, not by the collection.
- The settings of the application itself (operator identity, fallback quota
  limits, Celery queue) are described in
  [python_app](roles/python_app.md#knowledge).

Moving an installation whose worker used to write the virtual hosts itself:
give the custom-domain service another `website_custom_domain_config_prefix`
than the old files (`custom-domain-` was the prefix of knowledge), let the first
reconciliation register the existing domains in the service, then delete the old
`custom-domain-*.conf` files and reload nginx. Two files for one host name would
make nginx ignore one of them.

## What a run does and does not do

| Variable | Created when missing | Existing entry |
| --- | --- | --- |
| `website_custom_domain_clients` | the authorized client | left as it is: change it with the admin API |
| `website_mailler_clients` | the registry record | left as it is: `mailler clients update` or the API |
| `website_mailler_template_dirs` | the templates of the directory | updated from the files |
| `website_billing_saas_apps` | the SaaS application | left as it is: admin API or the internal UI |
| `website_billing_client_bindings` | the binding | nothing to do |

A second run reports no change, except for the template import, which only
reports a change when it created a template. Removing an entry from the
inventory does not remove it from the service.

The shell commands run as the account of the service with its environment file
(`DATABASE_URL`), so they work before any OAuth client can reach the API. They
are skipped in check mode.

## 3. Order of the first deployment

1. Deploy the services without clients: the migrations create no tenant.
2. Create the OAuth clients and grant the scopes (step 1).
3. Declare the clients in the inventory and run the playbook again.
4. For a database that already holds data, set
   `website_mailler_legacy_client_id` before the first run of the new version of
   `mailler` (migration 006 assigns the existing templates, contacts and
   campaigns to that client and stops if it is empty), and, for billing, leave
   `website_billing_partition_allow_unbound` at `true` only until the bindings
   exist.
5. Give each SaaS application its redirect allow-list
   (`checkout_urls`) before its first checkout, and set
   `website_billing_plans_public` only if the plans must be readable without a
   token.

## Checking the result

On the host of the service, as its account with the environment file loaded:

```bash
custom-domain list-clients
mailler clients list
mailler templates list --client-id <client id>
billing-admin saas list
billing-admin client list --saas my-app
```

## What is not covered

- The OAuth clients, their scopes and their secrets live at the authentication
  server. The collection neither creates nor reads them.
- Modifying an existing client, application or binding (see the table above).
- The upstream of a customer domain must be reachable from nginx, and the CNAME
  target must resolve to the nginx host with ports 80 and 443 open: see the
  [custom-domain documentation](../apps/custom-domain/index.md).
- None of this could be run against a real host, a PostgreSQL database or an
  authentication server when it was written: the commands were run against stand-ins
  of the CLIs, and the sudoers rules were compared with the output of
  `custom-domain sudoers`.
