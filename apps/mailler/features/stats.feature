Feature: Sending statistics
  Statistics are computed from the stored emails, in total, per provider and
  per day.

  Background:
    Given I am authenticated as client "bdd-client" with scopes "mailler:stats"

  Scenario: Statistics are empty when nothing was sent
    When I send a GET to "/api/v1/stats"
    Then the response status should be 200
    And the response JSON path "total.sent" should be "0"
    And the response JSON path "total.failed" should be "0"
    And the response JSON "by_provider" should be "{}"
    And the response JSON "by_date" should have 0 entries

  Scenario: Statuses are counted in total
    Given the following emails are stored for client "bdd-client"
      | to_email      | provider | status    |
      | a@example.com | brevo    | sent      |
      | b@example.com | brevo    | delivered |
      | c@example.com | ses      | bounced   |
      | d@example.com | ses      | failed    |
      | e@example.com | ses      | pending   |
    When I send a GET to "/api/v1/stats"
    Then the response status should be 200
    And the response JSON path "total.sent" should be "1"
    And the response JSON path "total.delivered" should be "1"
    And the response JSON path "total.bounced" should be "1"
    And the response JSON path "total.failed" should be "1"

  Scenario: Statistics are broken down by provider
    Given the following emails are stored for client "bdd-client"
      | to_email      | provider | status    |
      | a@example.com | brevo    | sent      |
      | b@example.com | brevo    | delivered |
      | c@example.com | ses      | failed    |
    When I send a GET to "/api/v1/stats"
    Then the response status should be 200
    And the response JSON path "by_provider.brevo.sent" should be "1"
    And the response JSON path "by_provider.brevo.delivered" should be "1"
    And the response JSON path "by_provider.ses.failed" should be "1"

  Scenario: Statistics can be limited to one provider
    Given the following emails are stored for client "bdd-client"
      | to_email      | provider | status |
      | a@example.com | brevo    | sent   |
      | b@example.com | ses      | sent   |
    When I send a GET to "/api/v1/stats?provider=ses"
    Then the response status should be 200
    And the response JSON path "total.sent" should be "1"
    And the response JSON path "by_provider.ses.sent" should be "1"
    And the response JSON "by_provider" should not have key "brevo"

  Scenario: Statistics are grouped by day
    Given the following emails are stored for client "bdd-client"
      | to_email      | provider | status |
      | a@example.com | brevo    | sent   |
      | b@example.com | brevo    | failed |
    When I send a GET to "/api/v1/stats"
    Then the response status should be 200
    And the response JSON "by_date" should have 1 entries

  Scenario: Emails outside the date range are ignored
    Given the following emails are stored for client "bdd-client"
      | to_email      | provider | status |
      | a@example.com | brevo    | sent   |
    When I send a GET to "/api/v1/stats?start_date=2020-01-01&end_date=2020-01-31"
    Then the response status should be 200
    And the response JSON path "total.sent" should be "0"

  Scenario: An invalid date is rejected
    When I send a GET to "/api/v1/stats?start_date=yesterday"
    Then the response status should be 422

  Scenario: Statistics require authentication
    Given I am not authenticated
    When I send a GET to "/api/v1/stats"
    Then the response status should be 401

  Scenario: Statistics require the stats scope
    Given I am authenticated with scopes "mailler:read"
    When I send a GET to "/api/v1/stats"
    Then the response status should be 403

  Scenario: Statistics only count the emails of the calling client
    Given the following emails are stored
      | to_email      | status | client_id  |
      | a@example.com | sent   | bdd-client |
      | b@example.com | sent   | other      |
      | c@example.com | failed | other      |
    When I send a GET to "/api/v1/stats"
    Then the response status should be 200
    And the response JSON path "total.sent" should be "1"
    And the response JSON path "total.failed" should be "0"

  Scenario: A client cannot ask for the statistics of another client
    When I send a GET to "/api/v1/stats?client_id=other"
    Then the response status should be 403

  Scenario: An administrator counts every client or narrows to one
    Given the following emails are stored
      | to_email      | status | client_id  |
      | a@example.com | sent   | bdd-client |
      | b@example.com | sent   | other      |
      | c@example.com | failed | other      |
    And I am authenticated as client "ops" with scopes "mailler:stats mailler:admin"
    When I send a GET to "/api/v1/stats"
    Then the response JSON path "total.sent" should be "2"
    And the response JSON path "total.failed" should be "1"
    When I send a GET to "/api/v1/stats?client_id=other"
    Then the response JSON path "total.sent" should be "1"
    And the response JSON path "total.failed" should be "1"
