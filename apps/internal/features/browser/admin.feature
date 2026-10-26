@browser
Feature: Admin dashboard and chat history in a browser
  As an operator with conversation permissions
  I want to follow the activity on the dashboard and manage the chat history
  So that I can monitor and administer the conversations

  # --- Dashboard ---

  Scenario: The dashboard summarizes the conversations
    Given a conversation exists with title "Hello World"
    And the conversation has a message with role "user" and content "Hi there"
    And another conversation exists with title "Second one"
    And the dashboard analytics are available
    And I sign in with the scopes "conversations:* analytics:read"
    When I navigate to "/"
    Then the page title should be "Dashboard - Internal Admin"
    And I should see "Chat Statistics"
    And I should see "Total Conversations"
    And I should see "Hello World"
    And I should see "Second one"
    And I should see "321"
    And the sidebar menu should highlight only "Dashboard"
    And the browser should report no errors

  Scenario: The dashboard hides the analytics from a user without the analytics scope
    Given the dashboard analytics are available
    And I sign in with the scopes "conversations:*"
    When I navigate to "/"
    Then I should see "Chat Statistics"
    And I should not see "Analytics (Last 30 days)"

  Scenario: The dashboard links to the analytics and to the conversations
    Given a conversation exists with title "Hello World"
    And the dashboard analytics are available
    And I sign in with the scopes "conversations:* analytics:read"
    When I navigate to "/"
    And I click "View Details →"
    Then the URL should be "/analytics"
    When I navigate to "/"
    And I click "View All Conversations →"
    Then the URL should be "/conversations"

  Scenario: The dashboard opens a recent conversation
    Given a conversation exists with title "Hello World"
    And I sign in with the scopes "conversations:*"
    When I navigate to "/"
    And I click "View"
    Then the URL should contain "/conversations/"
    And I should see "Conversation Information"

  Scenario: A user without conversation scopes gets the access denied page
    Given I sign in with the scopes "contacts:read"
    When I navigate to "/"
    Then the page title should contain "Access Denied"
    And I should see "conversations:read"
    And I should see "Logout"

  Scenario: The access denied page offers to log out
    Given I sign in with the scopes "contacts:read"
    And the provider ends every session
    When I navigate to "/conversations"
    And I click "Logout"
    Then the cookie "access_token" should not be set
    And I should be asked to sign in at the provider

  # --- Conversation list ---

  Scenario: The list shows the conversations with their number of messages
    Given a conversation exists with title "Hello World"
    And the conversation has a message with role "user" and content "Hi there"
    And I sign in with the scopes "conversations:*"
    When I navigate to "/conversations"
    Then the page title should be "Chat History - Internal Admin"
    And I should see "Conversations (1)"
    And I should see "Hello World"
    And I should see "1 messages"
    And the sidebar menu should highlight only "Chat History"

  Scenario: An empty history says so
    Given I sign in with the scopes "conversations:read"
    When I navigate to "/conversations"
    Then I should see "Conversations (0)"

  Scenario: Searching narrows the list to the matching session
    Given a conversation exists with session id "session-abc-123"
    And a conversation exists with title "Other chat"
    And I sign in with the scopes "conversations:*"
    When I navigate to "/conversations"
    And I fill "search" with "session-abc"
    And I click "Search"
    Then the URL should contain "search=session-abc"
    And I should see "Conversations (1)"
    And I should see "Anonymous Session"
    And I should not see "Other chat"

  Scenario: Filtering by type keeps only anonymous or authenticated conversations
    Given a conversation exists with session id "session-abc-123"
    And a conversation exists with title "Signed in chat"
    And I sign in with the scopes "conversations:*"
    When I navigate to "/conversations"
    And I select "Anonymous" from "type"
    Then the URL should contain "type=anonymous"
    And I should see "Anonymous Session"
    And I should not see "Signed in chat"

  Scenario: The list is paginated
    Given 25 conversations exist titled "Chat"
    And I sign in with the scopes "conversations:*"
    When I navigate to "/conversations"
    Then I should see "Page 1 of 2"
    And I should see "Chat 000"
    And I should not see "Chat 024"
    When I click "Next →"
    Then the URL should be "/conversations?page=2"
    And I should see "Page 2 of 2"
    And I should see "Chat 024"
    And I should not see "Chat 000"
    When I click "← Previous"
    Then I should see "Page 1 of 2"

  Scenario: The search is kept when moving to the next page
    Given 25 conversations exist titled "x&y"
    And a conversation exists with session id "x-other"
    And I sign in with the scopes "conversations:*"
    When I navigate to "/conversations"
    And I fill "search" with "x&y"
    And I click "Search"
    Then I should see "Conversations (25)"
    When I click "Next →"
    Then I should see "Page 2 of 2"
    And I should see "Conversations (25)"
    And I should see "x&y 024"

  # --- Conversation detail ---

  Scenario: The detail shows the owner and the messages
    Given a conversation exists with title "Hello World"
    And the conversation has a message with role "user" and content "Hi there"
    And the conversation has a message with role "assistant" and content "Hello, how can I help?"
    And the auth client returns user info for conversation owner
    And I sign in with the scopes "conversations:*"
    When I open the conversation I created
    Then the page title should be "Conversation Detail - Internal Admin"
    And I should see "Conversation Owner"
    And I should see "owner@test.local"
    And I should see "Hi there"
    And I should see "Hello, how can I help?"
    And the sidebar menu should highlight only "Chat History"
    When I click "Back to Conversations"
    Then the URL should be "/conversations"

  Scenario: A conversation that does not exist is reported
    Given I sign in with the scopes "conversations:*"
    When I navigate to "/conversations/00000000-0000-0000-0000-000000000099"
    Then I should see "Conversation not found"
    And the sidebar menu should highlight only "Chat History"

  # --- Deleting ---

  Scenario: Deleting a conversation asks for a confirmation and reports the success
    Given a conversation exists with title "To Delete"
    And I sign in with the scopes "conversations:*"
    When I open the conversation I created
    And I click "Delete Conversation"
    Then the page should have asked for a confirmation containing "permanently delete this conversation"
    And the URL should contain "/conversations?success="
    And I should see "Conversation deleted successfully"
    And I should see "Conversations (0)"

  Scenario: Dismissing the confirmation keeps the conversation
    Given a conversation exists with title "To Keep"
    And I sign in with the scopes "conversations:*"
    When I open the conversation I created
    And I dismiss the next confirmation
    And I click "Delete Conversation"
    Then the page should have asked for a confirmation containing "permanently delete"
    And the URL should contain "/conversations/"
    When I navigate to "/conversations"
    Then I should see "To Keep"

  Scenario: A user who cannot delete does not see the delete button
    Given a conversation exists with title "Read only"
    And I sign in with the scopes "conversations:read"
    When I open the conversation I created
    Then I should see "Conversation Information"
    And "Delete Conversation" should be hidden

  Scenario: Selected conversations are deleted in bulk
    Given a conversation exists with title "Bulk 1"
    And another conversation exists with title "Bulk 2"
    And I sign in with the scopes "conversations:*"
    When I navigate to "/conversations"
    And I click "css=#select-all"
    Then I should see "Delete Selected"
    When I click "Delete Selected"
    Then the page should have asked for a confirmation containing "delete 2 conversations"
    And I should see "2 conversation(s) deleted successfully"
    And I should see "Conversations (0)"

  Scenario: Clearing the selection hides the bulk actions
    Given a conversation exists with title "Bulk 1"
    And I sign in with the scopes "conversations:*"
    When I navigate to "/conversations"
    And I click "css=.conv-checkbox"
    Then "Delete Selected" should be visible
    When I click "Clear Selection"
    Then "Delete Selected" should be hidden
