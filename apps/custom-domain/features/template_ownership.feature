Feature: Per-client nginx template ownership
  A template is either shared by every client or owned by one client. A client can only put
  a shared template or one of its own on its domains, and the provisioning applies the same
  rule. Clients cannot create templates: an administrator does, for one client.

  Background:
    Given an authorized client "tenant-a" exists
    And an authorized client "tenant-b" exists
    And a template "shared" exists
    And a template "branded-a" is owned by "tenant-a"
    And a template "branded-b" is owned by "tenant-b"
    And the verification and provisioning queues are recorded

  Scenario: An administrator creates a template for one client
    Given I am authenticated as client "ops" with scopes "custom-domain:admin custom-domain:admin:templates"
    When I send a POST request to "/api/v1/admin/templates" with JSON
      """
      {"slug": "branded-c", "name": "Branded C", "client_id": "tenant-a",
       "http_template": "server { server_name {{ domain }}; }",
       "https_template": "server { listen 443 ssl; server_name {{ domain }}; }"}
      """
    Then the response status is 201
    And the JSON field "client_id" equals "tenant-a"

  Scenario: Listing the templates of one client or the shared ones
    Given I am authenticated as client "ops" with scopes "custom-domain:admin custom-domain:admin:templates"
    When I send a GET request to "/api/v1/admin/templates?client_id=tenant-b"
    Then the JSON field "total" equals "1"
    When I send a GET request to "/api/v1/admin/templates?shared=true"
    Then the JSON field "total" equals "1"
    When I send a GET request to "/api/v1/admin/templates"
    Then the JSON field "total" equals "3"

  Scenario: A client sees the shared templates and its own
    Given I am authenticated as client "tenant-a" with scopes "custom-domain:read"
    When I send a GET request to "/api/v1/templates"
    Then the response status is 200
    And the JSON field "total" equals "2"
    And the response does not contain "branded-b"
    And the response does not contain "http_template"

  Scenario: A client registers a domain with its own template
    Given I am authenticated as client "tenant-a" with scopes "custom-domain:read custom-domain:write"
    When I register the domain shop.example.com with the template "branded-a"
    Then the response status is 201

  Scenario: A client cannot use the template of another client
    Given I am authenticated as client "tenant-a" with scopes "custom-domain:read custom-domain:write"
    When I register the domain shop.example.com with the template "branded-b"
    Then the response status is 400
    And the JSON field "detail" contains "not available"

  Scenario: A client cannot switch a domain to the template of another client
    Given I am authenticated as client "tenant-a" with scopes "custom-domain:read custom-domain:write"
    And a domain "shop.example.com" with the status "active" in the database
    When I update the template of the domain "shop.example.com" to "branded-b"
    Then the response status is 400

  Scenario: A client-owned template cannot be the global default
    Given I am authenticated as client "ops" with scopes "custom-domain:admin custom-domain:admin:templates"
    When I send a POST request to "/api/v1/admin/templates/{template:branded-a}/set-default"
    Then the response status is 400
    And the JSON field "detail" contains "global default"

  Scenario: A client default template must be usable by that client
    Given I am authenticated as client "ops" with scopes "custom-domain:admin custom-domain:admin:clients"
    When I send a PUT request to the client "tenant-a" with the default template "branded-b"
    Then the response status is 400
    When I send a PUT request to the client "tenant-a" with the default template "branded-a"
    Then the response status is 200

  Scenario: Provisioning renders the default template of the client
    Given the client "tenant-a" has the default template "branded-a"
    And a domain "shop.example.com" with the status "dns_verified" in the database
    And certbot issues a certificate expiring in 90 days
    When the SSL provisioning task runs for "shop.example.com"
    Then the domain "shop.example.com" has the status "active"
    And the nginx configuration was rendered from the template "branded-a"

  Scenario: Provisioning ignores a template of another client
    Given a domain "shop.example.com" with the status "dns_verified" in the database
    And the domain "shop.example.com" uses the template "branded-b"
    And certbot issues a certificate expiring in 90 days
    When the SSL provisioning task runs for "shop.example.com"
    Then the nginx configuration was rendered with the packaged templates
