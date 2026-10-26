Feature: Event collection
  As a website owner
  I want to collect analytics events
  So that I can understand visitor behaviour

  Scenario: Collect an event via POST
    When I send a POST request to "/collect" with JSON
      """
      {
        "events": [
          {"event_type": "pageview", "page_url": "https://example.com", "page_title": "Home"}
        ]
      }
      """
    Then the response status code should be 200
    And the response should be valid JSON
    And the response JSON key "success" should equal "True"
    And the response JSON key "events_count" should equal "1"
    And the database should contain 1 session
    And the database should contain 1 event

  Scenario: Collect several events in one request
    When I send a POST request to "/collect" with JSON
      """
      {
        "events": [
          {"event_type": "pageview", "page_url": "https://example.com/page1"},
          {"event_type": "click", "event_data": {"element": "button"}},
          {"event_type": "pageview", "page_url": "https://example.com/page2"}
        ]
      }
      """
    Then the response status code should be 200
    And the response JSON key "events_count" should equal "3"
    And the database should contain 3 events

  Scenario: A request without events is rejected
    When I send a POST request to "/collect" with JSON
      """
      {"events": []}
      """
    Then the response status code should be 422
    And the database should contain 0 sessions

  Scenario: A new visitor receives a session cookie
    When I send a POST request to "/collect" with JSON
      """
      {"events": [{"event_type": "pageview"}]}
      """
    Then the response should set the session cookie "ua_sid"
    And the session cookie should be HttpOnly

  Scenario: A returning visitor keeps its session
    Given a first visit has been collected
    When the visitor comes back with its session cookie
    And I send a POST request to "/collect" with JSON
      """
      {"events": [{"event_type": "click"}]}
      """
    Then the response status code should be 200
    And the response should not set a session cookie
    And the database should contain 1 session
    And the database should contain 2 events

  Scenario: The beacon returns a transparent GIF and records the event
    When I send a GET request to "/collect?t=pageview&u=https://example.com"
    Then the response status code should be 200
    And the response should be a GIF image
    And the response header "Cache-Control" should contain "no-cache"
    And the response header "Pragma" should contain "no-cache"
    And the database should contain 1 event
    And the stored event should have type "pageview" and page URL "https://example.com"

  Scenario: The beacon accepts JSON encoded event data
    When I send a GET request to "/collect?t=click&d=%7B%22button%22%3A%22signup%22%7D"
    Then the response status code should be 200
    And the stored event should have data key "button" equal to "signup"

  Scenario: The beacon ignores event data that is not JSON
    When I send a GET request to "/collect?t=click&d=not-json"
    Then the response status code should be 200
    And the database should contain 1 event

  Scenario: The beacon requires an event type
    When I send a GET request to "/collect"
    Then the response status code should be 422

  Scenario: Device information is stored with the session
    Given the request header "User-Agent" is "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    When I send a POST request to "/collect" with JSON
      """
      {"events": [{"event_type": "pageview"}]}
      """
    Then the stored session should have device type "desktop" and browser "Chrome"

  Scenario: The client IP comes from the proxy header
    Given the request header "X-Forwarded-For" is "203.0.113.7, 10.0.0.1"
    When I send a POST request to "/collect" with JSON
      """
      {"events": [{"event_type": "pageview"}]}
      """
    Then the stored session should have IP address "203.0.113.7"

  Scenario: IP anonymization masks the last octet
    Given IP anonymization is enabled
    And the request header "X-Forwarded-For" is "203.0.113.7"
    When I send a POST request to "/collect" with JSON
      """
      {"events": [{"event_type": "pageview"}]}
      """
    Then the stored session should have IP address "203.0.113.0"

  Scenario: UTM parameters are stored with the session
    When I send a POST request to "/collect?utm_source=newsletter&utm_campaign=spring" with JSON
      """
      {"events": [{"event_type": "pageview"}]}
      """
    Then the stored session should have UTM source "newsletter" and campaign "spring"
