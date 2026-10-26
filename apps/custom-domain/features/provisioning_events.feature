Feature: Provisioning status and events
  A client can poll the status of a domain, read the events recorded while it was being
  provisioned and follow them live through a server-sent events stream. Redis is replaced
  by an in-process fake.

  Background:
    Given an authorized client "tenant-a" exists
    And I am authenticated as client "tenant-a" with scopes "custom-domain:read"

  Scenario: Polling the status of a pending domain
    Given a domain "shop.example.com" with the status "pending" in the database
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}/status"
    Then the response status is 200
    And the JSON field "status" equals "pending"
    And the progress is 0 percent

  Scenario: Polling the status of an active domain
    Given a domain "shop.example.com" with the status "active" in the database
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}/status"
    Then the progress is 100 percent
    And all 4 provisioning steps are completed

  Scenario: The status of a domain waiting for its certificate
    Given a domain "shop.example.com" with the status "ssl_provisioning" in the database
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}/status"
    Then the progress is 60 percent
    And the current step is "certbot"

  Scenario: The status of another client's domain is not accessible
    Given a stored domain "theirs.example.com" owned by client "tenant-b"
    When I send a GET request to "/api/v1/domains/{domain:theirs.example.com}/status"
    Then the response status is 403

  Scenario: Reading the recorded events
    Given a domain "shop.example.com" with the status "active" in the database
    And Redis holds these events for "shop.example.com"
      | type           | step       | message                       | timestamp                 |
      | completed      |            | done                          | 2026-01-01T10:05:00+00:00 |
      | step_completed | certbot    | certificate issued            | 2026-01-01T10:03:00+00:00 |
      | step_started   | certbot    | requesting the certificate    | 2026-01-01T10:01:00+00:00 |
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}/events/history"
    Then the response status is 200
    And the JSON field "events" has 3 items
    And the JSON field "has_more" is false

  Scenario: Reading the events since a given time
    Given a domain "shop.example.com" with the status "active" in the database
    And Redis holds these events for "shop.example.com"
      | type           | step       | message                       | timestamp                 |
      | step_completed | certbot    | certificate issued            | 2026-01-01T10:03:00+00:00 |
      | step_started   | certbot    | requesting the certificate    | 2026-01-01T10:01:00+00:00 |
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}/events/history?since=2026-01-01T10:02:00%2B00:00"
    Then the JSON field "events" has 1 items

  Scenario: Streaming an already completed domain
    Given a domain "shop.example.com" with the status "active" in the database
    And Redis publishes no live event
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}/events"
    Then the response status is 200
    And the stream carries the events "initial_state, completed"

  Scenario: Streaming the live events of a domain being provisioned
    Given a domain "shop.example.com" with the status "ssl_provisioning" in the database
    And Redis publishes these live events
      | type           | payload                                  |
      | step_completed | {"step": "certbot", "message": "issued"} |
      | completed      | {"status": "active"}                     |
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}/events"
    Then the stream carries the events "initial_state, step_completed, completed"

  Scenario: A deactivated client can not follow its domains
    Given the client "tenant-a" is deactivated
    And a domain "shop.example.com" with the status "pending" in the database
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}/status"
    Then the response status is 403
    And the JSON field "detail" equals "Client not authorized"

  Scenario: Polling the status of a domain being deleted
    Given a domain "shop.example.com" with the status "deprovisioning" in the database
    When I send a GET request to "/api/v1/domains/{domain:shop.example.com}/status"
    Then the response status is 200
    And the JSON field "status" equals "deprovisioning"
    And the progress is 0 percent
