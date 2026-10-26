Feature: Audio resampling between Asterisk and OpenAI formats
    As the call handler
    I need to convert audio between 8 kHz (Asterisk) and 24 kHz (OpenAI)
    So that call audio keeps its quality across the bridge

    Scenario: Resample silence from 8 kHz to 24 kHz
        Given 320 bytes of silence
        When I resample from 8 kHz to 24 kHz
        Then the output should be 960 bytes
        And all output samples should be zero

    Scenario: Resample a tone from 8 kHz to 24 kHz
        Given a 440 Hz tone at 8 kHz with 160 samples
        When I resample from 8 kHz to 24 kHz
        Then the output should contain 480 samples
        And the output should contain non-zero samples

    Scenario: Resample silence from 24 kHz to 8 kHz
        Given 960 bytes of silence
        When I resample from 24 kHz to 8 kHz
        Then all output samples should be zero

    Scenario: Resample a tone from 24 kHz to 8 kHz
        Given a 440 Hz tone at 24 kHz with 480 samples
        When I resample from 24 kHz to 8 kHz
        Then the output should contain 160 samples
        And the output should contain non-zero samples

    Scenario: Loud samples are clipped instead of wrapping around
        Given 160 samples at the maximum amplitude
        When I resample from 8 kHz to 24 kHz
        Then every output sample should stay within the 16-bit range

    Scenario: Empty or too short input gives no output
        Given 1 byte of audio
        When I resample from 8 kHz to 24 kHz
        Then the output should be 0 bytes

    Scenario: AudioBuffer accumulates data below the chunk size
        Given an AudioBuffer with chunk size 320
        When I add 100 bytes to the buffer
        Then the buffer should return no data
        When I add 220 bytes to the buffer
        Then the buffer should return 320 bytes

    Scenario: AudioBuffer splits large data into fixed-size chunks
        Given an AudioBuffer with chunk size 320
        When I add 700 bytes to the buffer as chunks
        Then I should receive 2 chunks of 320 bytes
        And flushing the buffer should return 60 bytes
