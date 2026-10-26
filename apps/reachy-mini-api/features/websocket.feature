Feature: WebSocket real-time communication
  As the Reachy Mini robot
  I want to keep a WebSocket connection open to the API
  So that I can receive real-time updates and send status reports

  Scenario: Connect and receive the welcome message
    When I connect to the WebSocket endpoint
    Then I should receive a message with type "connected"
    And the message field "message" should be "Connected to Reachy Mini API"
    And the message should contain "timestamp"

  Scenario: Ping returns a pong
    Given I am connected to the WebSocket endpoint
    When I send a WebSocket message with type "ping"
    Then I should receive a message with type "pong"
    And the message should contain "timestamp"

  Scenario: Status reports the open connections
    Given I am connected to the WebSocket endpoint
    When I send a WebSocket message with type "status"
    Then I should receive a message with type "status"
    And the message field "connections" should be at least 1

  Scenario: Broadcast reaches the connected clients
    Given I am connected to the WebSocket endpoint
    When I send a WebSocket broadcast with data "hello everyone"
    Then I should receive a message with type "broadcast"
    And the message field "data" should be "hello everyone"

  Scenario: Broadcast without data uses an empty object
    Given I am connected to the WebSocket endpoint
    When I send a WebSocket message with type "broadcast"
    Then I should receive a message with type "broadcast"
    And the message field "data" should be an empty object

  Scenario: Unknown message type returns an acknowledgment
    Given I am connected to the WebSocket endpoint
    When I send a WebSocket message with type "custom_command"
    Then I should receive a message with type "ack"
    And the message should contain "received"

  Scenario: Invalid JSON returns an error
    Given I am connected to the WebSocket endpoint
    When I send raw text "this is not valid json"
    Then I should receive a message with type "error"
    And the message field "message" should be "Invalid JSON"
