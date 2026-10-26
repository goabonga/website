Feature: Conversations and messages
  As the chat backend
  I want conversations and their messages stored per user or anonymous session
  So that history survives between requests

  Scenario: Creating a conversation for an anonymous session
    When a conversation is created for the session "abcdef12-3456-7890-abcd-ef1234567890"
    Then the conversation should be saved and committed
    And the conversation should belong to the session "abcdef12-3456-7890-abcd-ef1234567890"

  Scenario: The active conversation is reused
    Given the session "abcdef12-3456-7890-abcd-ef1234567890" already has an active conversation
    When the conversation of that session is requested
    Then the existing conversation should be returned
    And no new conversation should be created

  Scenario: A conversation is created when none is active
    Given the session "abcdef12-3456-7890-abcd-ef1234567890" has no active conversation
    When the conversation of that session is requested
    Then a new conversation should be created

  Scenario: Messages are stored with their role
    When the message "Hello" is added with the role "user"
    Then the stored message should have the role "user" and the content "Hello"

  Scenario: History is returned as role and content pairs
    Given the conversation contains the messages:
      | role      | content                   |
      | user      | Hello                     |
      | assistant | Hi there! How can I help? |
    When the conversation history is requested
    Then the history should be:
      | role      | content                   |
      | user      | Hello                     |
      | assistant | Hi there! How can I help? |

  Scenario: Archiving keeps the conversation but marks it
    Given the session "abcdef12-3456-7890-abcd-ef1234567890" already has an active conversation
    When the conversation of that session is archived
    Then the archived conversation should have an archive date
