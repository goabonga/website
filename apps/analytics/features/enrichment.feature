Feature: Visitor enrichment
  As the analytics service
  I want to derive device and location data from a request
  So that sessions carry useful context without third-party scripts

  Scenario Outline: User agents are classified
    When I parse the user agent "<user_agent>"
    Then the device type should be "<device_type>"
    And the browser should be "<browser>"
    And the operating system should be "<os>"

    Examples:
      | user_agent                                                                                                                       | device_type | browser | os      |
      | Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36                  | desktop     | Chrome  | Windows |
      | Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1 | mobile      | Mobile Safari | iOS     |
      | Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)                                                         | bot         | Googlebot | Other |

  Scenario: A missing user agent gives no device information
    When I parse an empty user agent
    Then the device type should be unknown
    And the visitor should not be flagged as a bot

  Scenario: Bots are flagged
    When I parse the user agent "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    Then the visitor should be flagged as a bot

  Scenario: GeoIP can be disabled
    Given GeoIP is disabled
    When I look up the location of "8.8.8.8"
    Then no country should be found
    And no city should be found

  Scenario: A missing GeoIP database disables lookups
    Given GeoIP is enabled with a database that does not exist
    When I look up the location of "8.8.8.8"
    Then no country should be found
    And GeoIP lookups should be switched off
