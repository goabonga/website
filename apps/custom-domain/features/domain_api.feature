Feature: Domain API
  Authorized clients register custom domains and follow them through verification and
  provisioning. The scenarios run the API against an in-memory database with a fake auth
  server; the Celery tasks and nginx are replaced by fakes.

  Background:
    Given an authorized client "tenant-a" exists
    And I am authenticated as client "tenant-a" with scopes "custom-domain:read custom-domain:write custom-domain:lookup"
    And the verification and provisioning queues are recorded

  Scenario: Registering a domain
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "Shop.Example.com", "owner_id": "org_1"}
      """
    Then the response status is 201
    And the JSON field "domain" equals "shop.example.com"
    And the JSON field "status" equals "pending"
    And the JSON field "cname_target" equals "apps.example.com"
    And the JSON field "dns_instructions" contains "CNAME"
    And DNS verification was queued for the new domain "shop.example.com"

  Scenario: An invalid domain name is refused
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "not a domain", "owner_id": "org_1"}
      """
    Then the response status is 400

  Scenario: A domain can only be registered once
    Given a domain "shop.example.com" with the status "pending" in the database
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "shop.example.com", "owner_id": "org_1"}
      """
    Then the response status is 409

  Scenario: An unknown client cannot register domains
    Given I am authenticated as client "stranger" with scopes "custom-domain:write"
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "shop.example.com", "owner_id": "org_1"}
      """
    Then the response status is 403
    And the JSON field "detail" equals "Client not authorized"

  Scenario: The domain quota of the client is enforced
    Given the client "tenant-a" may hold 1 domains
    And a domain "first.example.com" with the status "pending" in the database
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "second.example.com", "owner_id": "org_1"}
      """
    Then the response status is 403
    And the JSON field "detail" equals "Domain limit reached (1)"

  Scenario: Listing only shows the domains of the calling client
    Given a domain "mine.example.com" with the status "pending" in the database
    And a stored domain "theirs.example.com" owned by client "tenant-b"
    When I send a GET request to "/api/v1/domains"
    Then the response status is 200
    And the JSON field "total" equals "1"

  Scenario: An administrator sees the domains of every client
    Given I am authenticated as client "ops" with scopes "custom-domain:read custom-domain:admin"
    And a domain "mine.example.com" with the status "pending" in the database
    And a stored domain "theirs.example.com" owned by client "tenant-b"
    When I send a GET request to "/api/v1/domains"
    Then the JSON field "total" equals "2"

  Scenario: A domain of another client is not accessible
    Given a stored domain "theirs.example.com" owned by client "tenant-b"
    When I send a GET request to "/api/v1/domains/{domain:theirs.example.com}"
    Then the response status is 403

  Scenario: Looking up an active domain by name
    Given a domain "shop.example.com" with the status "active" in the database
    When I send a GET request to "/api/v1/domains/lookup/shop.example.com"
    Then the response status is 200
    And the JSON field "owner_id" equals "org_1"

  Scenario: Looking up a domain that is not active
    Given a domain "shop.example.com" with the status "pending" in the database
    When I send a GET request to "/api/v1/domains/lookup/shop.example.com"
    Then the response status is 404

  Scenario: Updating the upstream of a domain
    Given a domain "shop.example.com" with the status "active" in the database
    When I send a PUT request to "/api/v1/domains/{domain:shop.example.com}" with JSON
      """
      {"upstream_target": "/run/new.sock"}
      """
    Then the response status is 200
    And the JSON field "upstream_target" equals "/run/new.sock"

  Scenario: Looking up a domain of another client
    Given a stored domain "theirs.example.com" owned by client "tenant-b"
    And the stored domain "theirs.example.com" is active
    When I send a GET request to "/api/v1/domains/lookup/theirs.example.com"
    Then the response status is 404

  Scenario: An administrator can look up the domains of every client
    Given I am authenticated as client "ops" with scopes "custom-domain:lookup custom-domain:admin"
    And a stored domain "theirs.example.com" owned by client "tenant-b"
    And the stored domain "theirs.example.com" is active
    When I send a GET request to "/api/v1/domains/lookup/theirs.example.com"
    Then the response status is 200
    And the JSON field "client_id" equals "tenant-b"

  Scenario: A deactivated client is refused on every call
    Given the client "tenant-a" is deactivated
    And a domain "shop.example.com" with the status "active" in the database
    When I send a GET request to "/api/v1/domains"
    Then the response status is 403
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}"
    Then the response status is 403
    When I send a GET request to "/api/v1/domains/lookup/shop.example.com"
    Then the response status is 403
    When I send a DELETE request to "/api/v1/domains/{domain:shop.example.com}"
    Then the response status is 403

  Scenario: The CNAME target falls back to the setting
    Given the client "tenant-a" has no default CNAME target
    And the default CNAME target setting is "fallback.example.net"
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "shop.example.com", "owner_id": "org_1"}
      """
    Then the response status is 201
    And the JSON field "cname_target" equals "fallback.example.net"

  Scenario: A domain without any CNAME target is refused
    Given the client "tenant-a" has no default CNAME target
    And no default CNAME target is configured
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "shop.example.com", "owner_id": "org_1"}
      """
    Then the response status is 400

  Scenario: Deleting a domain is asynchronous: a worker removes it and frees the name
    Given a domain "shop.example.com" with the status "active" in the database
    And the deprovisioning queue is recorded
    When I send a DELETE request to "/api/v1/domains/{domain:shop.example.com}"
    Then the response status is 202
    And the JSON field "status" equals "deprovisioning"
    And deprovisioning was queued for the domain "shop.example.com"
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}"
    Then the JSON field "status" equals "deprovisioning"
    When I send a PUT request to "/api/v1/domains/{domain:shop.example.com}" with JSON
      """
      {"upstream_target": "/run/new.sock"}
      """
    Then the response status is 409
    When the deprovisioning task runs for "shop.example.com"
    And I send a GET request to "/api/v1/domains/{domain:shop.example.com}"
    Then the response status is 404
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "shop.example.com", "owner_id": "org_2"}
      """
    Then the response status is 201

  Scenario: Restarting the DNS verification of a failed domain
    Given a domain "shop.example.com" with the status "failed" in the database
    When I send a POST request to "/api/v1/domains/{domain:shop.example.com}/verify"
    Then the response status is 200
    And the JSON field "status" equals "dns_verifying"
    And DNS verification was queued for the new domain "shop.example.com"

  Scenario: An active domain cannot be verified again
    Given a domain "shop.example.com" with the status "active" in the database
    When I send a POST request to "/api/v1/domains/{domain:shop.example.com}/verify"
    Then the response status is 400

  Scenario: Triggering SSL provisioning of a verified domain
    Given a domain "shop.example.com" with the status "dns_verified" in the database
    When I send a POST request to "/api/v1/domains/{domain:shop.example.com}/provision"
    Then the response status is 200
    And the JSON field "status" equals "ssl_provisioning"
    And SSL provisioning was queued for the domain "shop.example.com"

  Scenario: A pending domain cannot be provisioned
    Given a domain "shop.example.com" with the status "pending" in the database
    When I send a POST request to "/api/v1/domains/{domain:shop.example.com}/provision"
    Then the response status is 400

  Scenario: The write scope is required to register domains
    Given I am authenticated as client "tenant-a" with scopes "custom-domain:read"
    When I send a POST request to "/api/v1/domains" with JSON
      """
      {"domain": "shop.example.com", "owner_id": "org_1"}
      """
    Then the response status is 403
