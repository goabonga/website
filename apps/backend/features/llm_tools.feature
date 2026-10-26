Feature: LLM client and tool registry
  As the chat orchestrator
  I want tools exposed to the model according to the caller's scopes
  So that the model can only call what the user is allowed to use

  Background:
    Given a tool registry with a public tool "echo" and a tool "report" requiring the scope "reports:read"

  Scenario: Anonymous callers only see public tools
    When the tools are listed for an anonymous user
    Then the listed tools should be "echo"

  Scenario: Callers with the scope see the restricted tool
    When the tools are listed for the scopes "openid, reports:read"
    Then the listed tools should be "echo, report"

  Scenario: A public tool is executed with the model arguments
    When the tool "echo" is executed with the text "hello"
    Then the tool should succeed with the data "hello"

  Scenario: A restricted tool is denied without its scope
    When the tool "report" is called by a caller with the scopes "openid" and the text "q3"
    Then the tool should fail with the error "Access denied: tool 'report' requires scopes: reports:read"

  Scenario: An unknown tool is reported
    When the tool "missing" is executed with the text "x"
    Then the tool should fail with the error "Tool 'missing' not found"

  Scenario: The built-in tools are registered
    Then the global registry should contain the tools "search_knowledge, get_session_info, auth_action, new_conversation, help_me"

  Scenario: Reasoning models use the completion token limit only
    Then the generation parameters for "gpt-4o-mini" should include a temperature
    And the generation parameters for "o3-mini" should not include a temperature

  Scenario: A chat completion is normalised
    Given the model answers "Bonjour" using 12 prompt tokens and 3 completion tokens
    When the client sends the message "Salut"
    Then the reply content should be "Bonjour"
    And the reported usage should be 12 prompt tokens and 3 completion tokens
