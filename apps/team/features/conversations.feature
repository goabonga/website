Feature: Conversations and messages
  A conversation is a thread in which agents exchange messages. Conversations
  and messages are managed under /platform/conversations; the conversations
  of a team are listed under /platform/{team_id}/conversations.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write team:read team:write"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I remember the response field "id" as "agent_id"

  Scenario: Creating a conversation
    When I send a POST request to "/platform/conversations" with the JSON '{"slug": "general", "title": "General chat"}'
    Then the response status is 201
    And the response JSON field "slug" is "general"
    And the response JSON field "type" is "general"
    And the response JSON field "status" is "active"
    And the response JSON field "team_id" is "None"

  Scenario: Reading and listing conversations
    Given I send a POST request to "/platform/conversations" with the JSON '{"slug": "general", "title": "General chat"}'
    And I remember the response field "id" as "conversation_id"
    And I send a POST request to "/platform/conversations" with the JSON '{"slug": "incident-1", "title": "Incident", "type": "incident"}'
    When I request "/platform/conversations/${conversation_id}"
    Then the response status is 200
    And the response JSON field "title" is "General chat"
    When I request "/platform/conversations"
    Then the response JSON list has 2 items

  Scenario: Reading an unknown conversation
    When I request "/platform/conversations/6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11"
    Then the response status is 404
    And the response detail is "Conversation not found"

  Scenario: Adding an agent to a conversation
    Given I send a POST request to "/platform/conversations" with the JSON '{"slug": "general", "title": "General chat"}'
    And I remember the response field "id" as "conversation_id"
    When I send a POST request to "/platform/conversations/${conversation_id}/agents/${agent_id}"
    Then the response status is 204
    And the conversation has 1 participants in the database

  Scenario: Adding an unknown agent to a conversation
    Given I send a POST request to "/platform/conversations" with the JSON '{"slug": "general", "title": "General chat"}'
    And I remember the response field "id" as "conversation_id"
    When I send a POST request to "/platform/conversations/${conversation_id}/agents/6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11"
    Then the response status is 404
    And the response detail is "Agent not found"

  Scenario: Posting and listing messages
    Given I send a POST request to "/platform/conversations" with the JSON '{"slug": "general", "title": "General chat"}'
    And I remember the response field "id" as "conversation_id"
    When I send a POST request to "/platform/conversations/${conversation_id}/messages" with the JSON '{"agent_id": "${agent_id}", "text": "Hello team", "content": {"mood": "happy"}}'
    Then the response status is 200
    And the response JSON field "text" is "Hello team"
    And the response JSON field "type" is "message"
    And the response JSON field "visibility" is "public"
    And the response JSON field "content.mood" is "happy"
    When I send a POST request to "/platform/conversations/${conversation_id}/messages" with the JSON '{"agent_id": "${agent_id}", "text": "Second", "type": "decision", "visibility": "private"}'
    And I request "/platform/conversations/${conversation_id}/messages"
    Then the response status is 200
    And the response JSON list has 2 items

  Scenario: Posting a message from an unknown agent
    Given I send a POST request to "/platform/conversations" with the JSON '{"slug": "general", "title": "General chat"}'
    And I remember the response field "id" as "conversation_id"
    When I send a POST request to "/platform/conversations/${conversation_id}/messages" with the JSON '{"agent_id": "6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11", "text": "Hello"}'
    Then the response status is 404
    And the response detail is "Agent not found"

  Scenario: Messages need the message scopes
    Given I send a POST request to "/platform/conversations" with the JSON '{"slug": "general", "title": "General chat"}'
    And I remember the response field "id" as "conversation_id"
    And I am authenticated with the scopes "team:platform:read team:platform:write"
    When I send a POST request to "/platform/conversations/${conversation_id}/messages" with the JSON '{"agent_id": "${agent_id}", "text": "Hello"}'
    Then the response status is 403
    When I request "/platform/conversations/${conversation_id}/messages"
    Then the response status is 403

  Scenario: Deleting a conversation deletes its messages
    Given I send a POST request to "/platform/conversations" with the JSON '{"slug": "general", "title": "General chat"}'
    And I remember the response field "id" as "conversation_id"
    And I send a POST request to "/platform/conversations/${conversation_id}/messages" with the JSON '{"agent_id": "${agent_id}", "text": "Hello"}'
    When I send a DELETE request to "/platform/conversations/${conversation_id}"
    Then the response status is 204
    And the database has 0 messages

  Scenario: Listing the conversations of a team
    Given a conversation "task-1" belongs to the team
    And a conversation "task-2" belongs to the team
    And I send a POST request to "/platform/conversations" with the JSON '{"slug": "general", "title": "General chat"}'
    When I request "/platform/${team_id}/conversations"
    Then the response status is 200
    And the response JSON list has 2 items
    When I request "/platform/${team_id}/conversations/count"
    Then the response status is 200
    And the response JSON field "count" is "2"

  Scenario: Listing the conversations of an unknown team
    When I request "/platform/6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11/conversations"
    Then the response status is 404
    And the response detail is "Team not found"
