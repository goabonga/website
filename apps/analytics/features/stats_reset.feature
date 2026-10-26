Feature: Analytics data reset
  As an administrator
  I want to erase all analytics data
  So that I can start from a clean state

  Background:
    Given a redirecting campaign "Spring sale" with destination "https://example.com/spring"
    And a pixel for the campaign "Spring sale" and recipient "alice@example.com"
    And a first visit has been collected
    And the pixel is opened and the campaign link is clicked

  Scenario: Resetting requires the delete scope
    Given I am authenticated with the scopes "analytics:read analytics:write"
    When I send a DELETE request to "/api/v1/stats/reset"
    Then the response status code should be 403
    And the database should contain 1 session

  Scenario: Resetting requires a token
    When I send a DELETE request to "/api/v1/stats/reset"
    Then the response status code should be 401

  Scenario: Reset deletes every analytics table
    Given I am authenticated with the scopes "analytics:delete"
    When I send a DELETE request to "/api/v1/stats/reset"
    Then the response status code should be 200
    And the response JSON key "success" should equal "True"
    And the response JSON key "sessions_deleted" should equal "1"
    And the response JSON key "events_deleted" should equal "1"
    And the response JSON key "campaigns_deleted" should equal "1"
    And the response JSON key "pixels_deleted" should equal "1"
    And the response JSON key "clicks_deleted" should equal "1"
    And the response JSON key "pixel_opens_deleted" should equal "1"
    And the database should be empty

  Scenario: Resetting an empty database deletes nothing
    Given I am authenticated with the scopes "analytics:delete"
    When I send a DELETE request to "/api/v1/stats/reset"
    And I send a DELETE request to "/api/v1/stats/reset"
    Then the response status code should be 200
    And the response JSON key "sessions_deleted" should equal "0"
    And the response JSON key "campaigns_deleted" should equal "0"
