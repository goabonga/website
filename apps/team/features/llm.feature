Feature: LLM completions
  Agents think with a language model. One function asks either OpenAI or
  Anthropic for a chat completion, with optional tool calling, and always
  returns the same structure: the text, the tool calls and why the model
  stopped. The providers are replaced by in-memory fakes.

  Scenario: OpenAI answers with text
    Given the OpenAI API answers "Hello there" and finishes with "stop"
    When a chat completion is requested from "openai" with the model "gpt-4o" and the message "Hi"
    Then the chat result content is "Hello there"
    And the chat result stop reason is "end_turn"
    And the chat result has 0 tool calls
    And the provider received the system prompt "You are helpful."
    And the provider received 1 messages

  Scenario: OpenAI asks to call a tool
    Given the OpenAI API answers with a call to "team_status" with the arguments '{"hours": 6}'
    When a chat completion with the tools "team_status" is requested from "openai" with the model "gpt-4o" and the message "Status?"
    Then the chat result stop reason is "tool_use"
    And the chat result has 1 tool calls
    And the tool call 1 is "team_status" with the arguments '{"hours": 6}'
    And the provider received the tool definitions "team_status" in the function calling format

  Scenario: OpenAI reports a truncated answer
    Given the OpenAI API answers "Cut" and finishes with "length"
    When a chat completion is requested from "openai" with the model "gpt-4o" and the message "Long"
    Then the chat result stop reason is "max_tokens"

  Scenario: Tool results are sent back to OpenAI in its own format
    Given the OpenAI API answers "Done" and finishes with "stop"
    When a chat completion is requested from "openai" after a tool call "call_1" to "team_status" that returned '{"agents": []}'
    Then the provider received the assistant tool call "call_1" and the tool message with the content '{"agents": []}'

  Scenario: Anthropic answers with text
    Given the Anthropic API answers "Bonjour" and stops with "end_turn"
    When a chat completion is requested from "anthropic" with the model "claude-sonnet-4-5" and the message "Hi"
    Then the chat result content is "Bonjour"
    And the chat result stop reason is "end_turn"
    And the provider received the system prompt "You are helpful."

  Scenario: Anthropic asks to call a tool
    Given the Anthropic API answers with a tool use "team_status" with the input '{"hours": 6}'
    When a chat completion with the tools "team_status" is requested from "anthropic" with the model "claude-sonnet-4-5" and the message "Status?"
    Then the chat result stop reason is "tool_use"
    And the tool call 1 is "team_status" with the arguments '{"hours": 6}'
    And the provider received the tool definitions "team_status" in the Anthropic format

  Scenario: Tool results are sent back to Anthropic in its own format
    Given the Anthropic API answers "Done" and stops with "end_turn"
    When a chat completion is requested from "anthropic" after a tool call "call_1" to "team_status" that returned '{"agents": []}'
    Then the provider received the tool use "call_1" and the tool result with the content '{"agents": []}'

  Scenario Outline: A provider needs its API key
    Given no API key is configured
    When a chat completion is requested from "<provider>" with the model "m" and the message "Hi"
    Then the request fails with "<error>"

    Examples:
      | provider  | error                              |
      | openai    | OPENAI_API_KEY is not configured    |
      | anthropic | ANTHROPIC_API_KEY is not configured |

  Scenario: An unknown provider is rejected
    When a chat completion is requested from "mistral" with the model "m" and the message "Hi"
    Then the request fails with "Unsupported provider: mistral"

  Scenario: A plain text completion
    Given the OpenAI API answers "Summary" and finishes with "stop"
    When a text completion is requested from "openai" with the model "gpt-4o" and the message "Summarize"
    Then the text completion is "Summary"
