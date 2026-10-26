Feature: Share notification emails
  When a package is shared with someone identified by an email address, the
  mailler service sends them a message that links to the package.

  Background:
    Given the repository serves components "main,private" of which "main" is public
    And a catalog with these indexed packages
      | name | owner | visibility | component |
      | tool | alice | private    | main      |
    And I am the signed-in user "alice"

  @database
  Scenario: Sharing with an email address sends a notification
    Given the mailler service is enabled
    When I share the package "tool" with user "bob@example.com"
    Then the response status is 303
    And the mailler service received a message for "bob@example.com"
    And the message subject mentions "tool"
    And the message links to the package page

  @database
  Scenario: Sharing with an opaque identifier sends nothing
    Given the mailler service is enabled
    When I share the package "tool" with user "sub-123"
    Then the mailler service received no message

  @database
  Scenario: Notifications are off when the email backend is not configured
    Given the mailler service is disabled
    When I share the package "tool" with user "bob@example.com"
    Then the response status is 303
    And the mailler service received no message

  @database
  Scenario: A mailler outage never blocks sharing
    Given the mailler service is enabled but failing
    When I share the package "tool" with user "bob@example.com"
    Then the response status is 303
    And the package "tool" is shared with "bob@example.com"
