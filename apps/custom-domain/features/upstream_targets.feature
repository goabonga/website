Feature: TCP upstream targets
  A domain can be served by an application that listens on a Unix socket or on a TCP
  address. Targets end up in generated nginx configuration, so anything that is not a
  socket path or host:port is refused.

  Background:
    Given an authorized client "tenant-a" exists
    And I am authenticated as client "tenant-a" with scopes "custom-domain:read custom-domain:write"
    And the verification and provisioning queues are recorded

  Scenario: A Unix socket is rendered with the unix: prefix
    Given a domain "shop.example.com" proxied to "/run/shop.sock"
    When I render the default HTTPS configuration
    Then the configuration contains "server unix:/run/shop.sock;"

  Scenario: A TCP address is rendered as is
    Given a domain "shop.example.com" proxied to "10.0.0.5:8000"
    When I render the default HTTPS configuration
    Then the configuration contains "server 10.0.0.5:8000;"
    And the configuration does not contain "unix:"

  Scenario: Registering a domain with a TCP upstream
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "shop.example.com", "owner_id": "org_1", "upstream_target": "app.internal:8000"}
      """
    Then the response status is 201
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}"
    Then the JSON field "upstream_target" equals "app.internal:8000"

  Scenario: An upstream that could inject configuration is refused
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "shop.example.com", "owner_id": "org_1", "upstream_target": "app:80; include /etc/passwd"}
      """
    Then the response status is 422

  Scenario: A URL is not an upstream
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "shop.example.com", "owner_id": "org_1", "upstream_target": "http://app.internal:8000"}
      """
    Then the response status is 422

  Scenario: Updating the upstream of a domain to a TCP address
    Given a domain "shop.example.com" with the status "active" in the database
    When I send a PUT request to "/api/v1/domains/{domain:shop.example.com}" with JSON
      """
      {"upstream_target": "[::1]:9000"}
      """
    Then the response status is 200
    And the JSON field "upstream_target" equals "[::1]:9000"

  Scenario: A client default must be a valid upstream
    Given I am authenticated as client "ops" with scopes "custom-domain:admin custom-domain:admin:clients"
    When I send a POST request to "/api/v1/admin/clients" with JSON
      """
      {"client_id": "tenant-b", "name": "B", "default_upstream_target": "app", "default_cname_target": "apps.example.com"}
      """
    Then the response status is 422

  Scenario: The command line refuses an invalid default upstream
    When I run the command "create-client --client-id tenant-c --name C --upstream http://app:80"
    Then the command fails
    And the output contains "--upstream"
