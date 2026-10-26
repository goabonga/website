Feature: Python client SDK
  The custom_domain.client package wraps the HTTP API. The scenarios point the SDK at the
  real application running in-process, with an in-memory database and a fake auth server.

  Background:
    Given an authorized client "tenant-a" exists
    And I am authenticated as client "tenant-a" with scopes "custom-domain:read custom-domain:write custom-domain:lookup"
    And the verification and provisioning queues are recorded
    And the SDK is connected to the service

  Scenario: Registering and reading a domain
    When I register the domain "shop.example.com" for the owner "org_1" with the SDK
    Then the SDK returns a pending domain with the CNAME target "apps.example.com"
    And the SDK can read the domain back

  Scenario: Listing domains with a status filter
    Given a domain "a.example.com" with the status "active" in the database
    And a domain "b.example.com" with the status "pending" in the database
    When I list the domains with the SDK filtered on the status "active"
    Then the SDK lists 1 domains

  Scenario: Looking up an active domain
    Given a domain "shop.example.com" with the status "active" in the database
    When I look up "shop.example.com" with the SDK
    Then the SDK returns the owner "org_1"

  Scenario: A missing domain raises NotFoundError
    When I read an unknown domain with the SDK
    Then the SDK raises "NotFoundError" with the status 404

  Scenario: A duplicate domain raises ConflictError
    Given a domain "shop.example.com" with the status "pending" in the database
    When I register the domain "shop.example.com" for the owner "org_1" with the SDK
    Then the SDK raises "ConflictError" with the status 409

  Scenario: An invalid domain raises ValidationError
    When I register the domain "not a domain" for the owner "org_1" with the SDK
    Then the SDK raises "ValidationError" with the status 400

  Scenario: A missing scope raises AuthorizationError
    Given I am authenticated as client "tenant-a" with scopes "custom-domain:read"
    And the SDK is connected to the service
    When I register the domain "shop.example.com" for the owner "org_1" with the SDK
    Then the SDK raises "AuthorizationError" with the status 403

  Scenario: Waiting for a domain that is already active
    Given a domain "shop.example.com" with the status "active" in the database
    When I wait for the domain "shop.example.com" to become active with the SDK
    Then the SDK returns the active domain "shop.example.com"

  Scenario: Waiting for a domain that failed
    Given a domain "shop.example.com" with the status "failed" in the database
    And the domain "shop.example.com" has the error "No CNAME record found"
    When I wait for the domain "shop.example.com" to become active with the SDK
    Then the SDK raises "CustomDomainError" mentioning "No CNAME record found"

  Scenario: An expired token is refreshed once
    Given the service rejects the first token and accepts a refreshed one
    When I list the domains with the SDK
    Then the token was refreshed 1 times

  Scenario: The administration namespaces
    Given I am authenticated as client "ops" with scopes "custom-domain:*"
    And the SDK is connected to the service
    And an authorized client "tenant-b" exists
    And a stored domain "one.example.com" owned by client "tenant-a"
    When I read the clients and the overview with the SDK
    Then the SDK reports 2 clients and 1 domains

  Scenario: The async client lists domains
    Given a domain "shop.example.com" with the status "active" in the database
    When I list the domains with the async SDK
    Then the SDK lists 1 domains

  Scenario: Deleting a domain reports the asynchronous deprovisioning
    Given a domain "shop.example.com" with the status "active" in the database
    And the deprovisioning queue is recorded
    When I delete the domain "shop.example.com" with the SDK
    Then the SDK reports the status "deprovisioning"
    And deprovisioning was queued for the domain "shop.example.com"
    When the deprovisioning task runs for "shop.example.com"
    And I read the domain "shop.example.com" with the SDK
    Then the SDK raises "NotFoundError" with the status 404

  Scenario: The async client verifies and provisions a domain
    Given a domain "shop.example.com" with the status "failed" in the database
    When the async SDK verifies the domain "shop.example.com"
    Then the SDK reports the status "dns_verifying"
    Given a domain "other.example.com" with the status "dns_verified" in the database
    When the async SDK provisions the domain "other.example.com"
    Then the SDK reports the status "ssl_provisioning"

  Scenario: The async client raises typed errors
    When the async SDK reads an unknown domain
    Then the SDK raises "NotFoundError" with the status 404
