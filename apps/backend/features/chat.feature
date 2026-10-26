Feature: Chat endpoint
  As a user of the API
  I want to send messages and receive responses
  So that I can interact with the AI assistant

  Background:
    Given the chat API is wired to a mock database

  # -- History Mode --

  Scenario: Anonymous user retrieves empty conversation history
    Given I am an anonymous user
    And the chat service returns an empty conversation history
    When I send a POST request to "/api/v1/chat?history=true" with body:
      """
      {"message": "ignored"}
      """
    Then the response status code should be 200
    And the response JSON "messages" should be an empty list
    And the response JSON "session_id" should not be null

  Scenario: Anonymous user retrieves existing conversation history
    Given I am an anonymous user
    And the chat service returns conversation history:
      | role      | content                   |
      | user      | Hello                     |
      | assistant | Hi there! How can I help? |
    When I send a POST request to "/api/v1/chat?history=true" with body:
      """
      {"message": "ignored"}
      """
    Then the response status code should be 200
    And the response JSON "messages" should have 2 items
    And the response JSON at "messages[0].role" should be "user"
    And the response JSON at "messages[0].content" should be "Hello"

  Scenario: Authenticated user retrieves history without session_id
    Given I am an authenticated user
    And the chat service returns an empty conversation history
    When I send a POST request to "/api/v1/chat?history=true" with body:
      """
      {"message": "ignored"}
      """
    Then the response status code should be 200
    And the response JSON "session_id" should be null

  # -- Streaming Mode --

  Scenario: Anonymous user sends a message and receives SSE stream
    Given I am an anonymous user
    And the chat orchestrator streams the following events:
      | type   | data                                                     |
      | intent | {"intent": "no_match"}                                   |
      | token  | {"content": "Hello"}                                     |
      | token  | {"content": " there"}                                    |
      | done   | {"usage": {"prompt_tokens": 10, "completion_tokens": 5}} |
    When I send a POST request to "/api/v1/chat" with body:
      """
      {"message": "Hi"}
      """
    Then the response status code should be 200
    And the response content type should contain "text/event-stream"
    And the SSE stream should contain an event of type "intent"
    And the SSE stream should contain an event of type "token"
    And the SSE stream should contain an event of type "done"

  Scenario: Streaming response includes correct headers
    Given I am an anonymous user
    And the chat orchestrator streams a minimal response
    When I send a POST request to "/api/v1/chat" with body:
      """
      {"message": "Test"}
      """
    Then the response status code should be 200
    And the response header "cache-control" should be "no-cache"
    And the response header "x-accel-buffering" should be "no"

  # -- Session Cookie --

  Scenario: New anonymous session sets a session cookie
    Given I am a new anonymous user with a freshly created session
    And the chat service returns an empty conversation history
    When I send a POST request to "/api/v1/chat?history=true" with body:
      """
      {"message": "hi"}
      """
    Then the response status code should be 200
    And the response should set a "session_id" cookie

  # -- Request Validation --

  Scenario: Missing message field returns validation error
    Given I am an anonymous user
    When I send a POST request to "/api/v1/chat" with body:
      """
      {}
      """
    Then the response status code should be 422

  # -- Rate Limiting --

  Scenario: Rate limited user receives 429 error
    Given I am a rate-limited user
    When I send a POST request to "/api/v1/chat" with body:
      """
      {"message": "hello"}
      """
    Then the response status code should be 429
