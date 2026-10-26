Feature: Security.txt Endpoint (RFC 9116)
  As a security researcher
  I want to access the security.txt file
  So that I can find vulnerability disclosure information

  Scenario: Security.txt returns required fields
    Given the security.txt settings are configured with:
      | field              | value                       |
      | security_contact   | mailto:security@example.com |
      | security_expires   | 2025-12-31T23:59:59Z        |
    When I send a GET request to "/.well-known/security.txt"
    Then the response status code should be 200
    And the response content type should be "text/plain"
    And the response body should contain "Contact: mailto:security@example.com"
    And the response body should contain "Expires: 2025-12-31T23:59:59Z"

  Scenario: Security.txt with all fields configured
    Given the security.txt settings are configured with:
      | field                        | value                                                       |
      | security_contact             | mailto:security@example.com                                 |
      | security_expires             | 2025-12-31T23:59:59Z                                        |
      | security_encryption          | https://example.com/pgp-key.txt                             |
      | security_acknowledgments     | https://example.com/thanks                                  |
      | security_preferred_languages | en, fr                                                      |
      | security_canonical           | https://example.com/.well-known/security.txt                |
      | security_policy              | https://example.com/security-policy                         |
      | security_hiring              | https://example.com/jobs                                    |
      | security_csaf                | https://example.com/.well-known/csaf/provider-metadata.json |
    When I send a GET request to "/.well-known/security.txt"
    Then the response status code should be 200
    And the response body should contain "Contact: mailto:security@example.com"
    And the response body should contain "Encryption: https://example.com/pgp-key.txt"
    And the response body should contain "Acknowledgments: https://example.com/thanks"
    And the response body should contain "Preferred-Languages: en, fr"
    And the response body should contain "Canonical: https://example.com/.well-known/security.txt"
    And the response body should contain "Policy: https://example.com/security-policy"
    And the response body should contain "Hiring: https://example.com/jobs"
    And the response body should contain "CSAF: https://example.com/.well-known/csaf/provider-metadata.json"

  Scenario: Security.txt with no fields configured
    Given the security.txt settings are configured with:
      | field            | value |
      | security_contact |       |
      | security_expires |       |
    When I send a GET request to "/.well-known/security.txt"
    Then the response status code should be 200
    And the response body should be empty
