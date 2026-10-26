Feature: Call handler bridging AudioSocket and OpenAI
    As the asterisk bot
    I need to bridge a phone call to an OpenAI Realtime conversation
    So that callers can talk to the assistant

    The telephony side is a fake Asterisk and the OpenAI side is a fake
    Realtime server; the real session and client classes run in between.

    Scenario: The bot speaks first with the configured voice and prompt
        Given a fake Asterisk call
        And OpenAI Realtime answering through a fake server
        And the bot is configured with voice "verse" and prompt "Be concise."
        When the call is handled
        Then the OpenAI session should use voice "verse" and prompt "Be concise."
        And a greeting request should have been sent to OpenAI

    Scenario: Caller audio is resampled and forwarded to OpenAI
        Given a fake Asterisk call
        And OpenAI Realtime answering through a fake server
        When the call is handled
        And Asterisk sends 2 audio frames of 320 bytes
        Then OpenAI should receive 1920 bytes of 24 kHz audio

    Scenario: Model audio is played to the caller in 20 ms frames
        Given a fake Asterisk call
        And OpenAI Realtime answering through a fake server
        When the call is handled
        And OpenAI sends 20 ms of audio
        Then Asterisk should receive a non-silent 320-byte audio frame

    Scenario: Silence is sent while the model is quiet
        Given a fake Asterisk call
        And OpenAI Realtime answering through a fake server
        When the call is handled
        And 100 ms pass without model audio
        Then Asterisk should receive only silent frames

    Scenario: The caller can interrupt the model
        Given a fake Asterisk call
        And OpenAI Realtime answering through a fake server
        When the call is handled
        And the model starts speaking
        And Asterisk sends 3 loud audio frames
        Then OpenAI should have been asked to cancel the response

    Scenario: The model hangs up after saying goodbye
        Given a fake Asterisk call
        And OpenAI Realtime answering through a fake server
        When the call is handled
        And OpenAI calls the hangup tool
        Then Asterisk should be told to hang up
        And the call should end

    Scenario: The call ends when Asterisk hangs up
        Given a fake Asterisk call
        And OpenAI Realtime answering through a fake server
        When the call is handled
        And Asterisk hangs up
        Then the call should end
        And the OpenAI connection should be closed

    Scenario: RAG adds the knowledge search tool and its instructions
        Given a fake Asterisk call
        And OpenAI Realtime answering through a fake server
        And RAG is enabled with a fake database
        When the call is handled
        Then the OpenAI session should declare the "search_knowledge" tool
        And the OpenAI session instructions should mention the knowledge base

    Scenario: A question is answered from the knowledge base
        Given a fake Asterisk call
        And OpenAI Realtime answering through a fake server
        And RAG is enabled with a fake database
        And the knowledge base contains the entries:
            | question             | answer                 |
            | What are your hours? | We are open 9am to 5pm |
        When the call is handled
        And OpenAI searches the knowledge base for "What are your hours?"
        Then OpenAI should receive the answer "We are open 9am to 5pm"

    Scenario: An unanswered question returns sample questions
        Given a fake Asterisk call
        And OpenAI Realtime answering through a fake server
        And RAG is enabled with a fake database
        And the knowledge base contains the entries:
            | question             | answer                 |
            | What are your hours? | We are open 9am to 5pm |
        When the call is handled
        And OpenAI searches the knowledge base for "bananas pyjamas zeppelin"
        Then OpenAI should be told that nothing was found
        And the sample questions should include "What are your hours?"
