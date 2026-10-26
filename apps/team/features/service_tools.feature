Feature: Service integration tools
  Agents can call the other services of the platform (billing, mailler,
  analytics, auth) through dedicated tools, or any internal service through
  service_call. The base URL and the token come from the credentials of the
  agent first, then from the global settings. The services are played in
  memory by an HTTP transport.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "OpsAgent", "role": "ops"}'
    And I remember the response field "id" as "agent_id"

  Scenario: service_call forwards a request to an internal service
    Given the services answer '{"sent": true}' with the status 200
    When the agent runs the tool "service_call" with '{"service": "mailer", "endpoint": "/api/ping", "method": "post", "body": {"a": 1}}' and the credentials '{"services_base_url": "http://services.internal", "services_api_key": "key-1"}'
    Then the tool result field "status_code" is "200"
    And the services received a POST request on "/mailer/api/ping"
    And the services received the bearer token "key-1"
    And the services received the JSON body '{"a": 1}'

  Scenario: service_call needs a base URL
    When the agent runs the tool "service_call" with '{"service": "mailer", "endpoint": "ping"}'
    Then the tool result field "error" is "Services base URL not configured"

  Scenario: Listing subscriptions on the billing service
    Given the services answer '{"items": [{"id": "sub_1"}]}' with the status 200
    When the agent runs the tool "billing_list_subscriptions" with '{"saas_id": "app-1", "status_filter": "active", "limit": 10}' and the credentials '{"billing_base_url": "http://billing.internal", "billing_token": "tok-b"}'
    Then the tool result field "items.0.id" is "sub_1"
    And the services received a GET request on "/platform/app-1/subscriptions"
    And the services received the query "status=active&limit=10"
    And the services received the bearer token "tok-b"

  Scenario: Reading a customer and a subscription
    Given the services answer '{"id": "cus_1"}' with the status 200
    When the agent runs the tool "billing_get_customer" with '{"saas_id": "app-1", "customer_id": "cus_1"}' and the credentials '{"billing_base_url": "http://billing.internal"}'
    Then the tool result field "id" is "cus_1"
    And the services received a GET request on "/platform/app-1/customers/cus_1"
    When the agent runs the tool "billing_get_subscription" with '{"saas_id": "app-1", "subscription_id": "sub_1"}' and the credentials '{"billing_base_url": "http://billing.internal"}'
    Then the services received a GET request on "/platform/app-1/subscriptions/sub_1"

  Scenario: Reporting usage to the billing service
    Given the services answer '{"recorded": true}' with the status 201
    When the agent runs the tool "billing_report_usage" with '{"saas_id": "app-1", "subscription_id": "sub_1", "quantity": 5, "action": "set"}' and the credentials '{"billing_base_url": "http://billing.internal"}'
    Then the tool result field "recorded" is "True"
    And the services received a POST request on "/usage/app-1/report"
    And the services received the JSON body '{"subscription_id": "sub_1", "quantity": 5, "action": "set"}'

  Scenario: An error of the billing service is returned to the agent
    Given the services answer 'no such customer' with the status 404
    When the agent runs the tool "billing_get_customer" with '{"saas_id": "app-1", "customer_id": "missing"}' and the credentials '{"billing_base_url": "http://billing.internal"}'
    Then the tool result field "error" is "Billing API error 404: no such customer"

  Scenario: Sending an email through the mailler service
    Given the services answer '{"id": "msg_1"}' with the status 201
    When the agent runs the tool "mailler_send_email" with '{"to_email": "user@example.com", "subject": "Hello", "html_content": "<p>Hi</p>"}' and the credentials '{"mailler_base_url": "http://mailler.internal"}'
    Then the tool result field "id" is "msg_1"
    And the services received a POST request on "/api/v1/send"
    And the services received the JSON body '{"to_email": "user@example.com", "subject": "Hello", "html_content": "<p>Hi</p>"}'

  Scenario: Starting a campaign through the mailler service
    Given the services answer '{"started": true}' with the status 200
    When the agent runs the tool "mailler_start_campaign" with '{"campaign_id": "c-1"}' and the credentials '{"mailler_base_url": "http://mailler.internal"}'
    Then the services received a POST request on "/api/v1/campaigns/c-1/send"

  Scenario: Reading the analytics overview
    Given the services answer '{"sessions": 12}' with the status 200
    When the agent runs the tool "analytics_overview" with '{"days": 7}' and the credentials '{"analytics_base_url": "http://analytics.internal"}'
    Then the tool result field "sessions" is "12"
    And the services received a GET request on "/api/v1/stats/overview"
    And the services received the query "days=7"

  Scenario: Listing users on the auth service
    Given the services answer '{"items": []}' with the status 200
    When the agent runs the tool "auth_list_users" with '{"search": "ann", "is_active": true}' and the credentials '{"auth_base_url": "http://auth.internal"}'
    Then the services received a GET request on "/admin/api/users"
    And the services received the query "search=ann&is_active=true"

  Scenario Outline: A tool without a configured service explains it
    When the agent runs the tool "<tool>" with '<params>'
    Then the tool result field "error" is "<error>"

    Examples:
      | tool                     | params                               | error                             |
      | billing_get_customer     | {"saas_id": "a", "customer_id": "c"} | Billing base URL not configured   |
      | mailler_start_campaign   | {"campaign_id": "c"}                 | Mailler base URL not configured   |
      | analytics_overview       | {}                                   | Analytics base URL not configured |
      | auth_list_roles          | {}                                   | Auth base URL not configured      |

  Scenario: The base URL falls back to the global setting
    Given the global billing base URL is "http://billing.global"
    And the services answer '{"id": "sub_1"}' with the status 200
    When the agent runs the tool "billing_get_subscription" with '{"saas_id": "app-1", "subscription_id": "sub_1"}'
    Then the services received a GET request on "/platform/app-1/subscriptions/sub_1"
    And the services received the bearer token "global-secret"

  Scenario: A Unix socket URL gets a dedicated client that must be closed
    When the service client is requested for "unix:///run/billing/billing.sock"
    Then the effective base URL is "http://localhost" and the client must be closed
    When the service client is requested for "http://billing.internal"
    Then the effective base URL is "http://billing.internal" and the client is shared
