Feature: Multi-tenant resolution
  As a platform operator
  I want each request to be attributed to a tenant from its address
  So that every workspace can be reached by path, subdomain or custom domain

  Background:
    Given the base domain "knowledge.example.test"
    And an active tenant "acme" with id "cccccccc-cccc-cccc-cccc-cccccccccccc"
    And the tenant "acme" has the active custom domain "docs.acme.test"
    And an API behind the tenant middleware

  Scenario: Resolve a tenant from a path prefix
    When a client requests "/t/acme/api/v1/ping" on host "knowledge.example.test"
    Then the response status code should be 200
    And the resolved tenant slug should be "acme"
    And the tenant should be resolved by "path"
    And the resolved tenant id should be "cccccccc-cccc-cccc-cccc-cccccccccccc"

  Scenario: Resolve a tenant from a subdomain
    When a client requests "/api/v1/ping" on host "acme.knowledge.example.test"
    Then the response status code should be 200
    And the resolved tenant slug should be "acme"
    And the tenant should be resolved by "subdomain"

  Scenario: Resolve a tenant from a custom domain
    When a client requests "/api/v1/ping" on host "docs.acme.test"
    Then the response status code should be 200
    And the resolved tenant slug should be "acme"
    And the tenant should be resolved by "custom_domain"

  Scenario: The main domain has no tenant
    When a client requests "/api/v1/ping" on host "knowledge.example.test"
    Then the response status code should be 200
    And no tenant should be resolved

  Scenario: An unknown subdomain is redirected to the main domain
    When a client requests "/api/v1/ping" on host "unknown.knowledge.example.test"
    Then the response status code should be 302
    And the redirect location should be "https://knowledge.example.test/api/v1/ping"

  Scenario: An invalid subdomain is ignored
    When a client requests "/api/v1/ping" on host "-bad-.knowledge.example.test"
    Then the response status code should be 200
    And no tenant should be resolved

  Scenario: An unknown host resolves to no tenant
    When a client requests "/api/v1/ping" on host "elsewhere.test"
    Then the response status code should be 200
    And no tenant should be resolved

  Scenario: A new tenant starts on the free plan
    When I create the tenant "Acme" with slug "acme-two"
    Then the new tenant should be on the "free" plan

  Scenario: A tenant slug must be subdomain safe
    When I try to create the tenant "Acme" with slug "Not Valid"
    Then the tenant creation should be rejected
