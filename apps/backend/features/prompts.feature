Feature: Scoped system prompts
  As the platform operator
  I want the assistant persona to depend on the scopes of the caller
  So that staff and visitors get an appropriate system prompt

  Background:
    Given the prompt cache is empty
    And the database holds the prompts:
      | slug    | default | scopes      | content                      |
      | general | yes     |             | You are the public assistant |
      | staff   | no      | staff:read  | You are the staff assistant  |
      | admin   | no      | staff:read, staff:write | You are the admin assistant |

  Scenario: Anonymous visitors get the default prompt
    When the prompt is requested for an anonymous user
    Then the prompt should be "You are the public assistant"

  Scenario: A user without the scopes gets the default prompt
    When the prompt is requested for the scopes "openid"
    Then the prompt should be "You are the public assistant"

  Scenario: A user with the scope gets the matching prompt
    When the prompt is requested for the scopes "openid, staff:read"
    Then the prompt should be "You are the staff assistant"

  Scenario: The most specific prompt wins
    When the prompt is requested for the scopes "staff:read, staff:write"
    Then the prompt should be "You are the admin assistant"

  Scenario: The selected prompt is cached
    When the prompt is requested for the scopes "staff:read"
    Then the scope cache should hold "You are the staff assistant"

  Scenario: A cached prompt avoids the database
    Given the cache already holds "Cached persona" for every caller
    When the prompt is requested for an anonymous user
    Then the prompt should be "Cached persona"
    And the database should not have been queried

  Scenario: The built-in prompt is used when no prompt exists
    Given the database holds no prompt
    When the prompt is requested for an anonymous user
    Then the prompt should be the built-in fallback
