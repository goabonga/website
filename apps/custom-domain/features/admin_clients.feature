Feature: Authorized client administration
  Only OAuth2 clients registered by an administrator can create domains. Every endpoint
  requires both the custom-domain:admin and custom-domain:admin:clients scopes.

  Background:
    Given I am authenticated as client "ops" with scopes "custom-domain:admin custom-domain:admin:clients"

  Scenario: Registering a client
    When I send a POST request to "/api/v1/admin/clients" with JSON
      """
      {
        "client_id": "tenant-a",
        "name": "Tenant A",
        "default_upstream_target": "/run/tenant-a.sock",
        "default_cname_target": "apps.example.com",
        "max_domains": 5
      }
      """
    Then the response status is 201
    And the JSON field "client_id" equals "tenant-a"
    And the JSON field "max_domains" equals "5"
    And the JSON field "is_active" is true

  Scenario: A client identifier can only be registered once
    Given an authorized client "tenant-a" exists
    When I send a POST request to "/api/v1/admin/clients" with JSON
      """
      {
        "client_id": "tenant-a",
        "name": "Again",
        "default_upstream_target": "/run/a.sock",
        "default_cname_target": "apps.example.com"
      }
      """
    Then the response status is 409

  Scenario: Listing clients reports their domain counts
    Given an authorized client "tenant-a" exists
    And a stored domain "shop.example.com" owned by client "tenant-a"
    When I send a GET request to "/api/v1/admin/clients"
    Then the response status is 200
    And the JSON field "total" equals "1"
    And the first client has the domain count 1

  Scenario: Updating a client changes only the given fields
    Given an authorized client "tenant-a" exists
    When I send a PUT request to "/api/v1/admin/clients/{client:tenant-a}" with JSON
      """
      {"name": "Renamed", "max_domains": 10}
      """
    Then the response status is 200
    And the JSON field "name" equals "Renamed"
    And the JSON field "max_domains" equals "10"
    And the JSON field "default_cname_target" equals "apps.example.com"

  Scenario: Deactivating and reactivating a client
    Given an authorized client "tenant-a" exists
    When I send a POST request to "/api/v1/admin/clients/{client:tenant-a}/deactivate"
    Then the response status is 200
    And the JSON field "is_active" is false
    When I send a POST request to "/api/v1/admin/clients/{client:tenant-a}/activate"
    Then the response status is 200
    And the JSON field "is_active" is true

  Scenario: Deleting a client without domains
    Given an authorized client "tenant-a" exists
    When I send a DELETE request to "/api/v1/admin/clients/{client:tenant-a}"
    Then the response status is 204

  Scenario: A client that owns domains cannot be deleted
    Given an authorized client "tenant-a" exists
    And a stored domain "shop.example.com" owned by client "tenant-a"
    When I send a DELETE request to "/api/v1/admin/clients/{client:tenant-a}"
    Then the response status is 400

  Scenario: An unknown client is reported
    When I send a GET request to "/api/v1/admin/clients/999"
    Then the response status is 404

  Scenario: The clients scope alone is not enough
    Given I am authenticated as client "ops" with scopes "custom-domain:admin:clients"
    When I send a GET request to "/api/v1/admin/clients"
    Then the response status is 403
