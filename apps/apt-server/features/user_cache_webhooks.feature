Feature: User cache kept in sync by webhooks
  The auth service signs user lifecycle events. apt-server verifies them and
  keeps a local copy of user profiles so owners and grantees can be shown by
  email instead of an opaque identifier.

  Background:
    Given the webhook secret is "whsec-test"

  @database
  Scenario: A created user is cached
    When the auth service sends a signed "user.created" event for user "u-1" with email "alice@example.com"
    Then the response status is 200
    And the user "u-1" is cached with email "alice@example.com"

  @database
  Scenario: An updated email replaces the cached one
    Given the user "u-1" is cached with email "old@example.com"
    When the auth service sends a signed "user.email_changed" event for user "u-1" with email "new@example.com"
    Then the user "u-1" is cached with email "new@example.com"

  @database
  Scenario: Access grants follow an email change
    Given a package "tool" owned by "alice" is shared with "old@example.com"
    When the auth service reports "user.email_changed" for user "u-1" changing email from "old@example.com" to "new@example.com"
    Then the package "tool" is shared with "new@example.com"

  @database
  Scenario: A deleted user is removed from the cache
    Given the user "u-1" is cached with email "alice@example.com"
    When the auth service sends a signed "user.deleted" event for user "u-1" with email "alice@example.com"
    Then the user "u-1" is not cached

  @database
  Scenario: An event with a bad signature is refused
    When the auth service sends an event signed with the wrong secret
    Then the response status is 401
    And the user "u-1" is not cached

  @database
  Scenario: Cached profiles resolve identifiers to display names
    Given the user "u-1" is cached with email "alice@example.com"
    Then the identifier "u-1" is displayed as "alice@example.com"
    And the identifier "unknown" is displayed as "unknown"
