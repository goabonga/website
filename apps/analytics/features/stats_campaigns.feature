Feature: Campaign statistics
  As a marketer
  I want to see how my campaigns perform
  So that I can compare clicks and email opens

  Background:
    Given a redirecting campaign "Spring sale" with destination "https://example.com/spring"
    And a pixel for the campaign "Spring sale" and recipient "alice@example.com"
    And a pixel for the campaign "Spring sale" and recipient "bob@example.com"
    And a redirecting campaign "Old offer" with destination "https://example.com/old"
    And the campaign "Old offer" is inactive

  Scenario: Campaign statistics require the read scope
    Given I am authenticated with the scopes "analytics:write"
    When I send a GET request to "/api/v1/stats/campaigns"
    Then the response status code should be 403

  Scenario: Campaigns are listed with their counters
    Given the first pixel of the campaign "Spring sale" is opened 2 times
    And the campaign link of "Spring sale" is clicked 3 times
    And I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/campaigns"
    Then the response status code should be 200
    And the campaign list entry "Spring sale" should have 2 pixels, 2 opens and 3 clicks

  Scenario: Inactive campaigns are hidden by default
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/campaigns"
    Then the response JSON list should have 1 item
    And the campaign list should not contain "Old offer"

  Scenario: Inactive campaigns can be included
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/campaigns?include_inactive=true"
    Then the response JSON list should have 2 items
    And the campaign list should contain "Old offer"

  Scenario: The number of campaigns can be limited
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/campaigns?include_inactive=true&limit=1"
    Then the response JSON list should have 1 item

  Scenario: Campaign detail
    Given the campaign link of "Spring sale" is clicked 3 times
    And I am authenticated with the scopes "analytics:read"
    When I request "/api/v1/stats/campaigns/{id}" for the campaign "Spring sale"
    Then the response status code should be 200
    And the response JSON key "name" should equal "Spring sale"
    And the response JSON key "destination_url" should equal "https://example.com/spring"
    And the response JSON key "click_count" should equal "3"
    And the campaign detail should have 1 day of clicks with 3 clicks

  Scenario: An unknown campaign is not found
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/campaigns/00000000-0000-0000-0000-000000000000"
    Then the response status code should be 404

  Scenario: A campaign identifier must be a UUID
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/campaigns/not-a-uuid"
    Then the response status code should be 422

  Scenario: Pixels of a campaign
    Given the first pixel of the campaign "Spring sale" is opened 2 times
    And I am authenticated with the scopes "analytics:read"
    When I request "/api/v1/stats/campaigns/{id}/pixels" for the campaign "Spring sale"
    Then the response status code should be 200
    And the response JSON list should have 2 items
    And the pixel list entry "alice@example.com" should have 2 opens
    And the pixel list entry "bob@example.com" should have 0 opens

  Scenario: Pixels can be paginated
    Given I am authenticated with the scopes "analytics:read"
    When I request "/api/v1/stats/campaigns/{id}/pixels?limit=1&offset=1" for the campaign "Spring sale"
    Then the response JSON list should have 1 item

  Scenario: Pixels of an unknown campaign are not found
    Given I am authenticated with the scopes "analytics:read"
    When I send a GET request to "/api/v1/stats/campaigns/00000000-0000-0000-0000-000000000000/pixels"
    Then the response status code should be 404
