Feature: security.txt
  The server publishes the vulnerability disclosure contact described by
  RFC 9116 at /.well-known/security.txt, built from its settings.

  Scenario: Configured fields are published as plain text
    Given the setting "security_contact" is "mailto:sec@example.test"
    And the setting "security_expires" is "2030-01-01T00:00:00Z"
    When I request "/.well-known/security.txt"
    Then the response status is 200
    And the response header "content-type" is "text/plain; charset=utf-8"
    And the response text is
      """
      Contact: mailto:sec@example.test
      Expires: 2030-01-01T00:00:00Z
      """

  Scenario: Optional fields follow the required ones and empty fields are omitted
    Given the setting "security_policy" is "https://example.test/policy"
    And the setting "security_contact" is "mailto:sec@example.test"
    And the setting "security_preferred_languages" is "en, fr"
    When I request "/.well-known/security.txt"
    Then the response text is
      """
      Contact: mailto:sec@example.test
      Preferred-Languages: en, fr
      Policy: https://example.test/policy
      """

  Scenario: Nothing is published when nothing is configured
    When I request "/.well-known/security.txt"
    Then the response status is 200
    And the response text is empty

  Scenario: security.txt is not served by the application page
    When I request "/.well-known/security.txt"
    Then the response body does not contain "<html"
