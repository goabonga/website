Feature: Email tracking pixels
  As a marketer
  I want to know when a campaign email is opened
  So that I can measure the reach of a campaign

  Scenario: Campaign tracking keys are unique
    Given a campaign "Spring sale"
    And a campaign "Autumn sale"
    Then the campaigns should have different tracking keys

  Scenario: Opening a pixel returns a transparent GIF
    Given a campaign "Spring sale"
    And a pixel for the campaign "Spring sale" and recipient "alice@example.com"
    When I send a GET request to the pixel URL
    Then the response status code should be 200
    And the response should be a GIF image
    And the response header "Cache-Control" should contain "no-cache"
    And the response header "Pragma" should contain "no-cache"
    And the response header "X-Content-Type-Options" should contain "nosniff"

  Scenario: An open is recorded
    Given a campaign "Spring sale"
    And a pixel for the campaign "Spring sale" and recipient "alice@example.com"
    When I send a GET request to the pixel URL
    Then the pixel should have been opened 1 time
    And the pixel first and last opened timestamps should be set
    And the database should contain 1 pixel open

  Scenario: Each open increments the counter
    Given a campaign "Spring sale"
    And a pixel for the campaign "Spring sale" and recipient "alice@example.com"
    When I send a GET request to the pixel URL
    And I send a GET request to the pixel URL
    And I send a GET request to the pixel URL
    Then the pixel should have been opened 3 times
    And the database should contain 3 pixel opens

  Scenario: The pixel is also served without the gif extension
    Given a campaign "Spring sale"
    And a pixel for the campaign "Spring sale" and recipient "alice@example.com"
    When I send a GET request to the pixel URL without extension
    Then the response should be a GIF image
    And the pixel should have been opened 1 time

  Scenario: The open records the client
    Given a campaign "Spring sale"
    And a pixel for the campaign "Spring sale" and recipient "alice@example.com"
    And the request header "User-Agent" is "MailClient/1.0"
    And the request header "X-Forwarded-For" is "203.0.113.9"
    When I send a GET request to the pixel URL
    Then the last pixel open should have user agent "MailClient/1.0" and IP address "203.0.113.9"

  Scenario: An unknown pixel still returns a GIF
    When I send a GET request to "/p/unknown-key.gif"
    Then the response status code should be 200
    And the response should be a GIF image
    And the database should contain 0 pixel opens

  Scenario: Deleting a campaign deletes its pixels and their opens
    Given a campaign "Spring sale"
    And a pixel for the campaign "Spring sale" and recipient "alice@example.com"
    When I send a GET request to the pixel URL
    And I delete the campaign "Spring sale"
    Then the database should contain 0 campaigns
    And the database should contain 0 pixels
    And the database should contain 0 pixel opens
