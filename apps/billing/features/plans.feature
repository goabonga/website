Feature: Public Plans
  The plans endpoint lists available pricing plans for a SaaS app by slug.

  Background:
    Given I am not authenticated

  Scenario: List plans for an existing SaaS app
    Given a SaaS app "Test App" with slug "test-plans" exists with products and prices
    When I send a GET to "/plans/test-plans"
    Then the response status should be 200
    And the response JSON "app_slug" should be "test-plans"
    And the response JSON should contain "plans"

  Scenario: List plans for a non-existent slug returns 404
    When I send a GET to "/plans/non-existent-slug"
    Then the response status should be 404

  Scenario: Plans expose the limits defined by the SaaS app
    Given a SaaS app "Limit App" with slug "limit-plans" has a plan "pro" with the limits '{"max_seats": 10, "emails_per_day": -1}'
    When I send a GET to "/plans/limit-plans"
    Then the response status should be 200
    And the limits of the plan "pro" should be '{"max_seats": 10, "emails_per_day": -1}'

  Scenario: Two SaaS apps expose different limit names for the same plan slug
    Given a SaaS app "Seat App" with slug "seat-plans" has a plan "pro" with the limits '{"max_seats": 5}'
    And a SaaS app "Mail App" with slug "mail-plans" has a plan "pro" with the limits '{"emails_per_day": 100}'
    When I send a GET to "/plans/seat-plans"
    Then the limits of the plan "pro" should be '{"max_seats": 5}'
