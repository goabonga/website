Feature: Campaign management API
  As a marketing tool
  I want to create campaigns and pixels through the API
  So that I can track a mailing without touching the database

  Scenario: Creating a campaign requires the write scope
    Given I am authenticated with the scopes "analytics:read"
    When I send a POST request to "/api/v1/stats/campaigns" with JSON
      """
      {"name": "Spring sale"}
      """
    Then the response status code should be 403

  Scenario: Create a campaign
    Given I am authenticated with the scopes "analytics:write"
    When I send a POST request to "/api/v1/stats/campaigns" with JSON
      """
      {
        "name": "Spring sale",
        "description": "Newsletter of April",
        "destination_url": "https://example.com/spring"
      }
      """
    Then the response status code should be 201
    And the response JSON key "name" should equal "Spring sale"
    And the response JSON key "is_active" should equal "True"
    And the response JSON key "destination_url" should equal "https://example.com/spring"
    And the database should contain 1 campaign

  Scenario: A campaign needs a name
    Given I am authenticated with the scopes "analytics:write"
    When I send a POST request to "/api/v1/stats/campaigns" with JSON
      """
      {"description": "No name"}
      """
    Then the response status code should be 422
    And the database should contain 0 campaigns

  Scenario: The tracking link of a new campaign works
    Given I am authenticated with the scopes "analytics:write"
    When I send a POST request to "/api/v1/stats/campaigns" with JSON
      """
      {"name": "Spring sale", "destination_url": "https://example.com/spring"}
      """
    And I remember the response JSON key "tracking_key" as "tracking_key"
    And I send a GET request to "/t/{tracking_key}" using the remembered values
    Then the response should be a redirect
    And the redirect location should start with "https://example.com/spring"

  Scenario: Create a pixel for a campaign
    Given I am authenticated with the scopes "analytics:write"
    And a campaign was created through the API
    When I send a POST request to "/api/v1/stats/campaigns/{campaign_id}/pixels" using the remembered values with JSON
      """
      {"recipient_email": "alice@example.com", "recipient_id": "42"}
      """
    Then the response status code should be 201
    And the response JSON key "recipient_email" should equal "alice@example.com"
    And the database should contain 1 pixel

  Scenario: The pixel of a new recipient records opens
    Given I am authenticated with the scopes "analytics:write"
    And a campaign was created through the API
    When I send a POST request to "/api/v1/stats/campaigns/{campaign_id}/pixels" using the remembered values with JSON
      """
      {"recipient_email": "alice@example.com"}
      """
    And I remember the response JSON key "pixel_key" as "pixel_key"
    And I send a GET request to "/p/{pixel_key}.gif" using the remembered values
    Then the response should be a GIF image
    And the database should contain 1 pixel open

  Scenario: Pixels cannot be created for an unknown campaign
    Given I am authenticated with the scopes "analytics:write"
    When I send a POST request to "/api/v1/stats/campaigns/00000000-0000-0000-0000-000000000000/pixels" with JSON
      """
      {"recipient_email": "alice@example.com"}
      """
    Then the response status code should be 404

  Scenario: Create several pixels at once
    Given I am authenticated with the scopes "analytics:write"
    And a campaign was created through the API
    When I send a POST request to "/api/v1/stats/campaigns/{campaign_id}/pixels/batch" using the remembered values with JSON
      """
      {
        "pixels": [
          {"recipient_email": "alice@example.com"},
          {"recipient_email": "bob@example.com"},
          {"recipient_id": "carol"}
        ]
      }
      """
    Then the response status code should be 201
    And the response JSON key "created_count" should equal "3"
    And the database should contain 3 pixels

  Scenario: Batch creation is refused for an unknown campaign
    Given I am authenticated with the scopes "analytics:write"
    When I send a POST request to "/api/v1/stats/campaigns/00000000-0000-0000-0000-000000000000/pixels/batch" with JSON
      """
      {"pixels": [{"recipient_email": "alice@example.com"}]}
      """
    Then the response status code should be 404

  Scenario: Delete a campaign with its pixels
    Given I am authenticated with the scopes "analytics:write"
    And a campaign was created through the API
    And a pixel was created for the remembered campaign
    When I send a DELETE request to "/api/v1/stats/campaigns/{campaign_id}" using the remembered values
    Then the response status code should be 204
    And the database should contain 0 campaigns
    And the database should contain 0 pixels

  Scenario: Deleting an unknown campaign is not found
    Given I am authenticated with the scopes "analytics:write"
    When I send a DELETE request to "/api/v1/stats/campaigns/00000000-0000-0000-0000-000000000000"
    Then the response status code should be 404

  Scenario: Deleting a campaign requires the write scope
    Given I am authenticated with the scopes "analytics:read"
    When I send a DELETE request to "/api/v1/stats/campaigns/00000000-0000-0000-0000-000000000000"
    Then the response status code should be 403
