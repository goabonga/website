Feature: Application foundation
    As an operator
    I want the daemon to read its settings from the environment
    So that I can deploy it without changing code

    Scenario: Default settings
        Given no AudioSocket or logging variable is set
        When the configuration is loaded
        Then the AudioSocket address should be "127.0.0.1:9092"
        And the log level should be "INFO"

    Scenario: Settings overridden by the environment
        Given the environment variable "AUDIOSOCKET_HOST" is "0.0.0.0"
        And the environment variable "AUDIOSOCKET_PORT" is "4000"
        And the environment variable "LOG_LEVEL" is "DEBUG"
        When the configuration is loaded
        Then the AudioSocket address should be "0.0.0.0:4000"
        And the log level should be "DEBUG"

    Scenario: Logging is split between stdout and stderr
        Given logging is configured on a clean root logger
        When an INFO record and an ERROR record are emitted
        Then the INFO record should go to stdout only
        And the ERROR record should go to stderr only

    Scenario: The effective configuration is logged
        Given the environment variable "AUDIOSOCKET_PORT" is "4001"
        And the configuration is loaded
        When the configuration is logged
        Then the log should mention "4001"
