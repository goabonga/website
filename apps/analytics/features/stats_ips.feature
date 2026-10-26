Feature: Per-IP statistics
  As an analyst
  I want to see which IP addresses are the most active
  So that I can spot heavy users and unusual traffic

  Background:
    Given the following sessions exist
      | session_id | country | device_type | browser | referrer                 | ip_address  | days_ago |
      | s1         | FR      | desktop     | Chrome  | https://news.example.com | 203.0.113.1 | 0        |
      | s2         | FR      | mobile      | Safari  |                          | 203.0.113.2 | 1        |
      | s3         | US      | desktop     | Firefox |                          | 203.0.113.1 | 2        |
      | s4         | DE      | desktop     | Chrome  |                          | 2001:db8::1 | 3        |
      | s5         | DE      | desktop     | Chrome  |                          | 203.0.113.9 | 90       |
    And the following events exist
      | session_id | event_type | page_url                | days_ago |
      | s1         | pageview   | https://example.com/    | 0        |
      | s1         | pageview   | https://example.com/faq | 0        |
      | s1         | click      |                         | 0        |
      | s3         | pageview   | https://example.com/    | 2        |
      | s2         | pageview   | https://example.com/    | 1        |
      | s4         | pageview   | https://example.com/v6  | 3        |

  Scenario: IP statistics require the read scope
    Given I am authenticated with the scopes "analytics:write"
    When I send a GET request to "/api/v1/stats/ips"
    Then the response status code should be 403

  Scenario: Most active IP addresses
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/ips"
    Then the response status code should be 200
    And the response JSON list should have 3 items
    And the first IP entry should be "203.0.113.1" with 2 sessions and 3 page views
    And the IP entry "203.0.113.1" should list the countries "FR, US"
    And the IP entry "203.0.113.1" should list the browsers "Chrome, Firefox"

  Scenario: The number of IP addresses can be limited
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/ips?limit=1"
    Then the response JSON list should have 1 item

  Scenario: Details of an IP address
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/ips/203.0.113.1"
    Then the response status code should be 200
    And the response JSON key "total_sessions" should equal "2"
    And the response JSON key "total_pageviews" should equal "3"
    And the response JSON key "total_events" should equal "4"
    And the IP detail should list the device types "desktop"
    And the IP detail should have 2 days of sessions
    And the IP detail page "https://example.com/" should have 2 page views
    And the IP detail event "click" should have a count of 1

  Scenario: Details of an IPv6 address
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/ips/2001:db8::1"
    Then the response status code should be 200
    And the response JSON key "total_sessions" should equal "1"

  Scenario: An unknown IP address is not found
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/ips/198.51.100.77"
    Then the response status code should be 404

  Scenario: Sessions outside the period are ignored
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/ips/203.0.113.9"
    Then the response status code should be 404
