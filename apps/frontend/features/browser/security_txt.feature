@browser
Feature: security.txt in a browser
  A visitor, or a security researcher, opens the disclosure contact of the
  site at the well-known address.

  Scenario: The contact is shown as plain text
    Given the setting "security_contact" is "mailto:sec@example.test"
    And the setting "security_expires" is "2030-01-01T00:00:00Z"
    And the setting "security_policy" is "https://example.test/policy"
    And the application is running
    When I visit "/.well-known/security.txt"
    Then the page answers 200
    And the content type of the page is "text/plain; charset=utf-8"
    And I should see "Contact: mailto:sec@example.test"
    And I should see "Expires: 2030-01-01T00:00:00Z"
    And I should see "Policy: https://example.test/policy"
    And I should not see "MENU"
    And the browser should report no errors

  Scenario: Nothing is published when nothing is configured
    Given the application is running
    When I visit "/.well-known/security.txt"
    Then the page answers 200
    And the content type of the page is "text/plain; charset=utf-8"
    And I should not see "Contact"
    And I should not see "MENU"
