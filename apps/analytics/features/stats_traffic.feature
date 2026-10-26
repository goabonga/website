Feature: Traffic statistics
  As a dashboard
  I want aggregated traffic figures
  So that I can show how the site is used

  Background:
    Given the following sessions exist
      | session_id | country | device_type | browser | referrer                 | ip_address | days_ago |
      | s1         | FR      | desktop     | Chrome  | https://news.example.com | 203.0.113.1 | 0       |
      | s2         | FR      | mobile      | Safari  |                          | 203.0.113.2 | 1       |
      | s3         | US      | desktop     | Firefox | https://news.example.com | 203.0.113.1 | 2       |
      | s4         | DE      | desktop     | Chrome  | https://blog.example.com | 203.0.113.4 | 90      |
    And the following events exist
      | session_id | event_type | page_url                | days_ago |
      | s1         | pageview   | https://example.com/    | 0        |
      | s1         | pageview   | https://example.com/faq | 0        |
      | s1         | click      |                         | 0        |
      | s2         | pageview   | https://example.com/    | 1        |
      | s3         | pageview   | https://example.com/    | 2        |
      | s4         | pageview   | https://example.com/old | 90       |

  Scenario: Statistics require a token
    When I send a GET request to "/api/v1/stats/overview"
    Then the response status code should be 401

  Scenario: Statistics require the read scope
    Given I am authenticated with the scopes "analytics:write"
    When I send a GET request to "/api/v1/stats/overview"
    Then the response status code should be 403

  Scenario: Overview of the last 30 days
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/overview"
    Then the response status code should be 200
    And the response JSON key "total_sessions" should equal "3"
    And the response JSON key "unique_visitors" should equal "2"
    And the response JSON key "total_pageviews" should equal "4"
    And the response JSON key "total_events" should equal "5"

  Scenario: The period can be widened
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/overview?days=365"
    Then the response JSON key "total_sessions" should equal "4"

  Scenario: The period is validated
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/overview?days=0"
    Then the response status code should be 422

  Scenario: Daily statistics
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/daily"
    Then the response status code should be 200
    And the response JSON list should have 3 items
    And the latest daily entry should have 1 session and 2 pageviews

  Scenario: Sessions by country
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/countries"
    Then the response status code should be 200
    And the entry "FR" of "country" should have 2 sessions and 66.67 percent

  Scenario: The number of countries can be limited
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/countries?limit=1"
    Then the response JSON list should have 1 item

  Scenario: Sessions by device type
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/devices"
    Then the entry "desktop" of "device_type" should have 2 sessions and 66.67 percent
    And the entry "mobile" of "device_type" should have 1 sessions and 33.33 percent

  Scenario: Sessions by browser
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/browsers"
    Then the entry "Chrome" of "browser" should have 1 sessions and 33.33 percent

  Scenario: Sessions by referrer ignore direct visits
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/referrers"
    Then the response JSON list should have 1 item
    And the entry "https://news.example.com" of "referrer" should have 2 sessions and 100.0 percent

  Scenario: Most visited pages count page views only
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/pages"
    Then the response JSON list should have 2 items
    And the page "https://example.com/" should have 3 page views and 3 unique sessions

  Scenario: Events by type
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/events"
    Then the event type "pageview" should have 4 events and 3 unique sessions
    And the event type "click" should have 1 events and 1 unique sessions
