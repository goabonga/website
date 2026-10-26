Feature: Admin dashboard and conversation management
  As an admin user with conversation permissions
  I want to view the dashboard and manage conversations
  So that I can monitor and administer chat history

  Background:
    Given I am a super admin

  # --- Dashboard ---

  Scenario: View admin dashboard
    Given the auth client returns a user for the dashboard
    When I send a GET request to "/"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View admin dashboard unauthenticated
    Given I am not authenticated
    When I send a GET request to "/"
    Then the response status code should be 302

  # --- Conversations list ---

  Scenario: List conversations when empty
    When I send a GET request to "/conversations"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: List conversations with data
    Given a conversation exists with title "Hello World"
    And the conversation has a message with role "user" and content "Hi there"
    When I send a GET request to "/conversations"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: List conversations with search filter
    Given a conversation exists with session id "session-abc-123"
    When I send a GET request to "/conversations?search=session-abc"
    Then the response status code should be 200
    And the response should be HTML

  # --- Conversation detail ---

  Scenario: View conversation detail
    Given a conversation exists with title "Test Conversation"
    And the conversation has a message with role "user" and content "Hello"
    And the conversation has a message with role "assistant" and content "Hi there!"
    And the auth client returns user info for conversation owner
    When I view the conversation detail
    Then the response status code should be 200
    And the response should be HTML

  Scenario: View conversation detail not found
    When I send a GET request to "/conversations/00000000-0000-0000-0000-000000000099"
    Then the response status code should be 200
    And the response should contain "Conversation not found"

  # --- Delete conversation ---

  Scenario: Delete a conversation
    Given a conversation exists with title "To Delete"
    When I delete the conversation
    Then the response status code should be 303
    And I should be redirected to a URL containing "success=Conversation+deleted"

  # --- Bulk delete ---

  Scenario: Bulk delete conversations
    Given a conversation exists with title "Bulk 1"
    And another conversation exists with title "Bulk 2"
    When I bulk delete the created conversations
    Then the response status code should be 303
    And I should be redirected to a URL containing "conversation(s)+deleted+successfully"

  Scenario: Bulk delete conversations with empty list
    When I send a POST request to "/conversations/bulk-delete" with form data
      | field            | value |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=No+conversations+selected"

  # --- Sidebar ---

  Scenario: Sidebar on the admin dashboard
    Given I am authenticated with only the scopes "conversations:*" granted by token exchange
    And the auth client returns a user for the dashboard
    When I send a GET request to "/"
    Then the response status code should be 200
    And the active sidebar link should be "/"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the conversations list
    Given I am authenticated with only the scopes "conversations:*" granted by token exchange
    When I send a GET request to "/conversations"
    Then the response status code should be 200
    And the active sidebar link should be "/conversations"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the conversation detail
    Given I am authenticated with only the scopes "conversations:*" granted by token exchange
    And a conversation exists with title "Hello World"
    And the conversation has a message with role "user" and content "Hi there"
    And the auth client returns user info for conversation owner
    When I view the conversation detail
    Then the response status code should be 200
    And the active sidebar link should be "/conversations"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the missing conversation
    Given I am authenticated with only the scopes "conversations:*" granted by token exchange
    When I send a GET request to "/conversations/00000000-0000-0000-0000-000000000099"
    Then the response status code should be 200
    And the active sidebar link should be "/conversations"
    And the sidebar should show the user "admin@test.local"
