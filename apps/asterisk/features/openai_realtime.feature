Feature: OpenAI Realtime client
    As the call handler
    I need a WebSocket client for the OpenAI Realtime API
    So that I can stream audio and tool calls with the model

    Scenario: Connecting configures the session
        Given a fake OpenAI Realtime server
        When the client connects
        Then the client should be connected with an authorization header
        And a session.update message should have been sent
        And the session should use server-side voice activity detection
        And the session should declare the hangup tool
        And the session should carry the system prompt

    Scenario: Custom tools are declared next to the hangup tool
        Given a fake OpenAI Realtime server
        And the client has a custom tool named "lookup"
        When the client connects
        Then the session should declare the tools "hangup, lookup"

    Scenario: Sending audio
        Given a connected client
        When the client sends 960 bytes of PCM audio
        Then an input_audio_buffer.append message should carry the base64 audio

    Scenario: Receiving audio
        Given a connected client
        And an audio callback is registered
        When OpenAI sends an audio delta
        Then the audio callback should receive the decoded PCM bytes

    Scenario: Receiving the caller transcript
        Given a connected client
        And a transcript callback is registered
        When OpenAI sends the transcript "hello there"
        Then the transcript callback should receive "hello there"

    Scenario: Sending a text message asks for a response
        Given a connected client
        When the client sends the text "Say hello"
        Then a user message with the text "Say hello" should have been sent
        And a response.create message should follow

    Scenario: A tool call is answered and a new response requested
        Given a connected client
        And a tool call callback returning "found"
        When OpenAI calls the tool "search_knowledge"
        Then the tool callback should receive the tool name and arguments
        And a function_call_output with the result should have been sent
        And a response.create message should follow

    Scenario: A hangup tool call does not request a new response
        Given a connected client
        And a tool call callback returning nothing
        When OpenAI calls the tool "hangup"
        Then a function_call_output reporting success should have been sent
        But no response.create message should follow

    Scenario: The caller interrupts the model
        Given a connected client
        And an interrupt callback is registered
        When OpenAI starts a response
        And OpenAI detects speech from the caller
        Then a response.cancel message should have been sent
        And the interrupt callback should have been called

    Scenario: Response state is tracked
        Given a connected client
        When OpenAI starts a response
        Then the client should be responding
        When OpenAI finishes the response
        Then the client should not be responding

    Scenario: Disconnecting
        Given a connected client
        When the client disconnects
        Then the WebSocket should be closed
        And the client should be marked as disconnected
