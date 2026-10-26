@browser
Feature: A feature carrying the tag

  Scenario: Every scenario of the feature gets a page
    When I open "/hello" with the raw page
    Then the raw page title is "Page /hello"
