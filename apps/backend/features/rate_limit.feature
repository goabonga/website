Feature: Redis rate limiting
  As the platform operator
  I want requests and session creations to be rate limited
  So that anonymous visitors cannot overload or abuse the API

  Background:
    Given a rate limiter backed by an in-memory Redis
    And the limits are 2 anonymous, 3 authenticated per window and 1 new session per IP

  Scenario: Anonymous requests are allowed until the limit is reached
    When an anonymous client "203.0.113.7" makes 2 requests
    Then every request should be allowed
    When an anonymous client "203.0.113.7" makes 1 requests
    Then the last request should be rejected

  Scenario: Limits are tracked per client address
    Given an anonymous client "203.0.113.7" has used its quota
    When an anonymous client "198.51.100.9" makes 1 requests
    Then every request should be allowed

  Scenario: Authenticated users get a higher limit
    When the user "12345678-1234-5678-1234-567812345678" makes 3 requests
    Then every request should be allowed
    When the user "12345678-1234-5678-1234-567812345678" makes 1 requests
    Then the last request should be rejected

  Scenario: Remaining quota is reported
    When an anonymous client "203.0.113.7" makes 1 requests
    Then the remaining quota should be 1

  Scenario: Session creation is limited per address
    When the address "203.0.113.7" creates a session
    Then the address "203.0.113.7" may not create another session
    And the address "198.51.100.9" may create a session

  Scenario: Client address honours proxy headers
    Given an API that echoes the client address
    When I request "/ip" with the header "X-Forwarded-For" set to "203.0.113.7, 10.0.0.1"
    Then the response JSON should contain "ip" with value "203.0.113.7"
    When I request "/ip" with the header "X-Real-IP" set to "198.51.100.9"
    Then the response JSON should contain "ip" with value "198.51.100.9"
