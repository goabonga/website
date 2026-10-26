Feature: Policy caching
  As a sending mail server
  I want the policy response to carry a cache lifetime
  So that I can reuse it for as long as the policy is valid

  Scenario: Response has a cache-control header
    When I send a GET request to "/.well-known/mta-sts.txt"
    Then the response header "cache-control" should contain "max-age=86400"

  Scenario: Cache lifetime follows the configured max age
    Given the setting "mta_sts_max_age" is "3600"
    When I send a GET request to "/.well-known/mta-sts.txt"
    Then the response header "cache-control" should contain "max-age=3600"
