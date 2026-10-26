Feature: Server-side page view analytics
  When an analytics service is configured, the server reports every page view
  to it, except requests for static files. Delivery never affects responses.

  Background:
    Given an analytics service

  Scenario: A page view is reported once the application stops
    Given the setting "analytics_url" is "https://ua.test"
    When I request "/pricing"
    And the application stops
    Then the analytics service received a "page_view_server" event for "/pricing"

  Scenario: Static files are not tracked
    Given the setting "analytics_url" is "https://ua.test"
    When I request "/static/assets/index.js"
    And I request "/pricing"
    And the application stops
    Then the analytics service received 1 event
    And the analytics service received a "page_view_server" event for "/pricing"

  Scenario: The client address comes from the forwarding headers
    Given the setting "analytics_url" is "https://ua.test"
    When I send "/pricing" with header "X-Forwarded-For" set to "4.4.4.4, 10.0.0.1"
    And the application stops
    Then the analytics service received the address "4.4.4.4"

  Scenario: Events are posted to the collect endpoint of the service
    Given the setting "analytics_url" is "https://ua.test/"
    When I request "/pricing"
    And the application stops
    Then the analytics service was called on "https://ua.test/collect"

  Scenario: Nothing is reported when no analytics service is configured
    When I request "/pricing"
    And the application stops
    Then the analytics service received 0 events

  Scenario: A failing analytics service does not affect the responses
    Given the analytics service is failing
    And the setting "analytics_url" is "https://ua.test"
    When I request "/health"
    And the application stops
    Then the response status is 200
