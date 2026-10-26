Feature: Administration statistics
  Administrators get counters about domains, clients and templates. Every endpoint requires
  both the custom-domain:admin and custom-domain:admin:stats scopes.

  Background:
    Given I am authenticated as client "ops" with scopes "custom-domain:admin custom-domain:admin:stats"

  Scenario: Overview of an empty service
    When I send a GET request to "/api/v1/admin/stats/overview"
    Then the response status is 200
    And the overview reports 0 domains, 0 clients and 0 templates

  Scenario: Overview counters follow the domain statuses
    Given a domain "a.example.com" with the status "active" in the database
    And a domain "b.example.com" with the status "pending" in the database
    And a domain "c.example.com" with the status "ssl_provisioning" in the database
    And a domain "d.example.com" with the status "failed" in the database
    And a domain "e.example.com" with the status "active" in the database
    And the domain "e.example.com" is soft-deleted
    When I send a GET request to "/api/v1/admin/stats/overview"
    Then the overview counts these domains
      | counter | value |
      | total   | 5     |
      | active  | 1     |
      | pending | 2     |
      | failed  | 1     |
      | deleted | 1     |

  Scenario: Certificates close to expiry are reported
    Given a domain "soon.example.com" with the status "active" in the database
    And the certificate of "soon.example.com" expires in 10 days
    And a domain "late.example.com" with the status "active" in the database
    And the certificate of "late.example.com" expires in 90 days
    And a domain "gone.example.com" with the status "active" in the database
    And the certificate of "gone.example.com" expires in -2 days
    When I send a GET request to "/api/v1/admin/stats/overview"
    Then the overview counts these domains
      | counter           | value |
      | ssl_expiring_soon | 1     |
      | ssl_expired       | 1     |

  Scenario: Clients and templates are counted
    Given an authorized client "tenant-a" exists
    And an authorized client "tenant-b" exists
    And the client "tenant-b" is deactivated
    And a template "static-site" exists
    When I send a GET request to "/api/v1/admin/stats/overview"
    Then the overview reports 0 domains, 2 clients and 1 templates
    And the JSON object "clients" has "inactive" equal to 1

  Scenario: Top clients are ranked by domain count
    Given an authorized client "small" exists
    And an authorized client "big" exists
    And a stored domain "one.example.com" owned by client "small"
    And a stored domain "two.example.com" owned by client "big"
    And a stored domain "three.example.com" owned by client "big"
    When I send a GET request to "/api/v1/admin/stats/top-clients"
    Then the top clients are "big, small"

  Scenario: Recent activity lists the latest domains first
    Given a domain "old.example.com" with the status "active" in the database
    And a domain "new.example.com" with the status "pending" in the database
    When I send a GET request to "/api/v1/admin/stats/recent-activity?limit=1"
    Then the JSON list has 1 items

  Scenario: The dashboard combines the three views
    Given an authorized client "tenant-a" exists
    And a stored domain "one.example.com" owned by client "tenant-a"
    When I send a GET request to "/api/v1/admin/stats/dashboard"
    Then the response status is 200
    And the dashboard has an overview, 1 top clients and 1 recent activities

  Scenario: The stats scope alone is not enough
    Given I am authenticated as client "ops" with scopes "custom-domain:admin:stats"
    When I send a GET request to "/api/v1/admin/stats/overview"
    Then the response status is 403
