Feature: MTA-STS policy
  As a sending mail server
  I want to retrieve the MTA-STS policy
  So that I can enforce TLS for email delivery (RFC 8461)

  Scenario: Serve the policy at the well-known URL
    When I send a GET request to "/.well-known/mta-sts.txt"
    Then the response status code should be 200
    And the response content type should be "text/plain"

  Scenario: Default policy content
    When I send a GET request to "/.well-known/mta-sts.txt"
    Then the response should contain "version: STSv1"
    And the response should contain "mode: enforce"
    And the response should contain "mx: mail.goabonga.com"
    And the response should contain "max_age: 86400"

  Scenario: Policy has a key-value structure
    When I send a GET request to "/.well-known/mta-sts.txt"
    Then the policy should have 4 lines
    And each line should match the pattern "^[a-z_]+: .+"

  Scenario: Testing mode is served when configured
    Given the setting "mta_sts_mode" is "testing"
    When I send a GET request to "/.well-known/mta-sts.txt"
    Then the response should contain "mode: testing"

  Scenario: One mx line per configured host
    Given the setting "mta_sts_mx" is "mx1.example.com, mx2.example.com"
    When I send a GET request to "/.well-known/mta-sts.txt"
    Then the response should contain "mx: mx1.example.com"
    And the response should contain "mx: mx2.example.com"
    And the policy should have 5 lines

  Scenario: Configured max age is rendered
    Given the setting "mta_sts_max_age" is "3600"
    When I send a GET request to "/.well-known/mta-sts.txt"
    Then the response should contain "max_age: 3600"
