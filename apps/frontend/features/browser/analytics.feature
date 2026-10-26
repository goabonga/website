@browser
Feature: Page view analytics in a browser
  Browsing the site is reported to the analytics service by the server, over
  HTTP, when the running application stops; static files are not reported.

  Background:
    Given an analytics collector

  Scenario: Page views are reported to the analytics service
    Given the application is running
    When I navigate to "/pricing"
    And I navigate to "/about"
    And the running application stops
    Then the analytics collector received a "page_view_server" event for "/pricing"
    And the analytics collector received a "page_view_server" event for "/about"

  Scenario: Static files are not reported
    Given the web client is built
    And the application is running
    When I navigate to "/"
    Then "MENU" should be visible
    When the running application stops
    Then the analytics collector received a "page_view_server" event for "/"
    And the analytics collector received no "page_view_server" event for "/static/assets/index.js"

  @cross-origin
  Scenario: The web client reports the page view itself
    Given the web client is built
    And the application is running
    When I navigate to "/pricing"
    Then the analytics collector received a "pageview" event for "/pricing"
