Feature: AudioSocket server
    As the Asterisk PBX
    I want to stream a call to the bot with the AudioSocket protocol
    So that audio flows in both directions

    Scenario: The server hands an accepted connection to its handler
        Given an AudioSocket server listening on a free loopback port
        When a client connects and sends a UUID packet
        Then the handler should receive a session carrying that UUID

    Scenario: The channel UUID is parsed
        Given an AudioSocket session connected to a fake Asterisk
        When Asterisk sends a UUID packet and closes the stream
        Then the session should store the UUID

    Scenario: Caller audio is passed to the audio callback
        Given an AudioSocket session connected to a fake Asterisk
        And an audio callback is registered on the session
        When Asterisk sends an audio packet of 320 bytes and closes the stream
        Then the audio callback should receive 320 bytes

    Scenario: Silence indicators are ignored
        Given an AudioSocket session connected to a fake Asterisk
        And an audio callback is registered on the session
        When Asterisk sends a silence packet and closes the stream
        Then the audio callback should not be called

    Scenario: A short audio frame is padded to 320 bytes
        Given an AudioSocket session connected to a fake Asterisk
        When the bot sends a frame of 100 bytes
        Then Asterisk should receive one audio packet with a 320-byte payload

    Scenario: A long audio frame is truncated to 320 bytes
        Given an AudioSocket session connected to a fake Asterisk
        When the bot sends a frame of 500 bytes
        Then Asterisk should receive one audio packet with a 320-byte payload

    Scenario: Audio is split into 20 ms frames
        Given an AudioSocket session connected to a fake Asterisk
        When the bot sends 700 bytes of audio
        Then Asterisk should receive 3 audio packets with a 320-byte payload

    Scenario: Hangup from Asterisk ends the session
        Given an AudioSocket session connected to a fake Asterisk
        When Asterisk sends a hangup packet
        Then the session should be inactive

    Scenario: An error packet ends the session
        Given an AudioSocket session connected to a fake Asterisk
        When Asterisk sends an error packet saying "call failed"
        Then the session should be inactive

    Scenario: A dropped connection ends the session quietly
        Given an AudioSocket session connected to a fake Asterisk
        When Asterisk drops the connection
        Then the session should be inactive

    Scenario: The bot hangs up the call
        Given an AudioSocket session connected to a fake Asterisk
        When the bot sends a hangup
        Then Asterisk should receive a hangup packet
        And the session should be inactive
