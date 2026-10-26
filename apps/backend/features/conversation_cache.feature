Feature: Conversation cache and background sync
  As the chat backend
  I want messages written to Redis first and persisted in the background
  So that answering a message does not wait for PostgreSQL

  Background:
    Given a conversation cache backed by an in-memory Redis

  Scenario: A new conversation is cached
    When a cached conversation is created for the session "abcdef12-3456-7890-abcd-ef1234567890"
    Then the conversation should be readable from the cache
    And the conversation should have no dirty flag

  Scenario: Adding a message marks the conversation dirty
    Given a cached conversation exists for the session "abcdef12-3456-7890-abcd-ef1234567890"
    When the message "Hello" is added to the cached conversation with the role "user"
    Then the cached conversation should contain 1 message
    And the conversation should be listed as dirty

  Scenario: Syncing writes the messages to the database and clears the flag
    Given a cached conversation exists for the session "abcdef12-3456-7890-abcd-ef1234567890"
    And the message "Hello" is added to the cached conversation with the role "user"
    When the dirty conversations are synced
    Then 1 conversation should have been synced
    And the database should have received the conversation and 1 message
    And the conversation should have no dirty flag

  Scenario: Invalidating removes the conversation from Redis only
    Given a cached conversation exists for the session "abcdef12-3456-7890-abcd-ef1234567890"
    When the cached conversation is invalidated
    Then the conversation should not be in the cache

  Scenario: The sync task is scheduled by Celery beat
    Then the Celery beat schedule should run "sync_dirty_conversations" every 30 seconds
    And the Celery application should use the "backend" queue
