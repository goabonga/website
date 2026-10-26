Feature: security.txt
  As a security researcher
  I want to find the security contact information
  So that I can report vulnerabilities (RFC 9116)

  Scenario: Empty security.txt when nothing is configured
    Given no security.txt field is configured
    When I send a GET request to "/.well-known/security.txt"
    Then the response status code should be 200
    And the response content type should be "text/plain"
    And the response body should be empty

  Scenario: Configured fields are published
    Given the security.txt field "contact" is "mailto:security@example.com"
    And the security.txt field "expires" is "2030-01-01T00:00:00Z"
    When I send a GET request to "/.well-known/security.txt"
    Then the response status code should be 200
    And the response should contain "Contact: mailto:security@example.com"
    And the response should contain "Expires: 2030-01-01T00:00:00Z"

  Scenario: Optional fields use their RFC 9116 names
    Given the security.txt field "preferred_languages" is "en, fr"
    And the security.txt field "policy" is "https://example.com/policy"
    When I send a GET request to "/.well-known/security.txt"
    Then the response should contain "Preferred-Languages: en, fr"
    And the response should contain "Policy: https://example.com/policy"
