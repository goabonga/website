Feature: Campaign link tracking
  As an email marketer
  I want to track the clicks on the links of a campaign
  So that I can measure engagement

  Scenario: A campaign link redirects to its destination
    Given a redirecting campaign "Spring sale" with destination "https://example.com/landing"
    When I send a GET request to the campaign link
    Then the response should be a redirect
    And the redirect location should start with "https://example.com/landing"
    And the redirect location should contain "utm_content="

  Scenario: A click is recorded
    Given a redirecting campaign "Spring sale" with destination "https://example.com/landing"
    When I send a GET request to the campaign link
    And I send a GET request to the campaign link
    Then the campaign "Spring sale" should have 2 clicks
    And the database should contain 2 campaign clicks

  Scenario: The click records the client and the referrer
    Given a redirecting campaign "Spring sale" with destination "https://example.com/landing"
    And the request header "User-Agent" is "MailClient/1.0"
    And the request header "Referer" is "https://mail.example.com/inbox"
    And the request header "X-Forwarded-For" is "203.0.113.9"
    When I send a GET request to the campaign link
    Then the last click should have user agent "MailClient/1.0", referrer "https://mail.example.com/inbox" and IP address "203.0.113.9"

  Scenario: UTM parameters of the request are preserved
    Given a redirecting campaign "Spring sale" with destination "https://example.com/landing"
    When I send a GET request to the campaign link with query "utm_source=newsletter&utm_medium=email"
    Then the redirect location should contain "utm_source=newsletter"
    And the redirect location should contain "utm_medium=email"

  Scenario: Query parameters are appended to a destination that already has some
    Given a redirecting campaign "Spring sale" with destination "https://example.com/landing?ref=1"
    When I send a GET request to the campaign link with query "utm_source=newsletter"
    Then the redirect location should contain "landing?ref=1&utm_source=newsletter"

  Scenario: The destination can be overridden with the url parameter
    Given a redirecting campaign "Spring sale" with destination "https://example.com/landing"
    When I send a GET request to the campaign link with query "url=https://example.com/other"
    Then the redirect location should start with "https://example.com/other"
    And the campaign "Spring sale" should have 1 click

  Scenario: An inactive campaign is not tracked
    Given a redirecting campaign "Spring sale" with destination "https://example.com/landing"
    And the campaign "Spring sale" is inactive
    When I send a GET request to the campaign link
    Then the response should be a redirect
    And the campaign "Spring sale" should have 0 clicks
    And the database should contain 0 campaign clicks

  Scenario: An unknown key redirects to the fallback page
    When I send a GET request to "/t/unknown-tracking-key"
    Then the response should be a redirect
    And the database should contain 0 campaign clicks

  Scenario: An unknown key can still use the url override
    When I send a GET request to "/t/test-key?url=https://example.com/landing"
    Then the redirect location should start with "https://example.com/landing"

  Scenario: Deleting a campaign deletes its clicks
    Given a redirecting campaign "Spring sale" with destination "https://example.com/landing"
    When I send a GET request to the campaign link
    And I delete the campaign "Spring sale"
    Then the database should contain 0 campaign clicks
