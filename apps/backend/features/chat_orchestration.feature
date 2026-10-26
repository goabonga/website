Feature: Chat orchestration and SSE streaming
  As the chat endpoint
  I want a message routed to tools or answered directly, and streamed back
  So that the user sees the answer token by token

  Background:
    Given an orchestrator whose conversation "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" has no history

  Scenario: A message without a matching tool is answered by the persona
    Given no tool applies to the message
    And the model streams the tokens "Hello", " there"
    When the user "Hi" is processed as the session "abcdef12-3456-7890-abcd-ef1234567890"
    Then the event types should be "history, intent, token, token, done"
    And the intent should be "no_match"
    And the streamed answer should be "Hello there"
    And the stored messages should be "user: Hi, assistant: Hello there"

  Scenario: A tool result is added to the model context
    Given the tool "get_session_info" answers "authenticated as Alice"
    And the model streams the tokens "You are Alice"
    When the user "Who am I?" is processed as the session "abcdef12-3456-7890-abcd-ef1234567890"
    Then the event types should be "history, intent, tools, token, done"
    And the intent should be "tool_call"
    And the model context should mention "authenticated as Alice"

  Scenario: Token usage is reported in the final event
    Given no tool applies to the message
    And the model streams the tokens "Ok" and reports 10 prompt tokens and 4 completion tokens
    When the user "Hi" is processed as the session "abcdef12-3456-7890-abcd-ef1234567890"
    Then the final event should report 10 prompt tokens and 4 completion tokens

  Scenario: Events are formatted as Server-Sent Events
    Given no tool applies to the message
    And the model streams the tokens "Hello"
    When the user "Hi" is processed and converted to SSE
    Then the SSE body should contain "event: intent"
    And the SSE body should contain "event: token"
    And the SSE body should contain "event: done"

  Scenario: A failure is reported as an error event
    Given the model fails while streaming
    When the user "Hi" is processed and converted to SSE
    Then the SSE body should contain "event: error"
