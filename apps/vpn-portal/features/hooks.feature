Feature: OpenVPN hook script
  As the OpenVPN server
  I want hook scripts that talk to the portal
  So that clients with revoked or expired certificates cannot connect and sessions are recorded

  The scenarios run the real script against the real portal application: the HTTP calls of
  the script are served in-process by the ASGI application and the OAuth2 server is a mock.

  Background:
    Given I am authenticated with "vpn:server" scope

  Scenario: A valid certificate is allowed to connect and its routes are pushed
    Given a certificate with common name "vpn-alice-1" is valid
    And OpenVPN reports the client "vpn-alice-1" from "203.0.113.7" with VPN address "10.8.0.6"
    When OpenVPN runs the connect hook
    Then the hook should exit with code 0
    And the routes file should contain 'push "route 10.0.0.0 255.0.0.0"'
    And the routes file should contain 'push "route 10.8.0.0 255.255.255.0"'
    And an active connection should be recorded for "vpn-alice-1" from "10.8.0.6"

  Scenario: A revoked certificate is denied
    Given a certificate with common name "vpn-bob-1" is revoked
    And OpenVPN reports the client "vpn-bob-1" from "203.0.113.8" with VPN address "10.8.0.7"
    When OpenVPN runs the connect hook
    Then the hook should exit with code 1
    And no connection should be recorded

  Scenario: An expired certificate is denied
    Given a certificate with common name "vpn-carol-1" is expired
    And OpenVPN reports the client "vpn-carol-1" from "203.0.113.9" with VPN address "10.8.0.8"
    When OpenVPN runs the connect hook
    Then the hook should exit with code 1

  Scenario: An unknown certificate is denied
    Given OpenVPN reports the client "vpn-ghost-1" from "203.0.113.10" with VPN address "10.8.0.9"
    When OpenVPN runs the connect hook
    Then the hook should exit with code 1

  Scenario: A connect event without common name is denied
    Given OpenVPN reports no common name
    When OpenVPN runs the connect hook
    Then the hook should exit with code 1

  Scenario: Disconnection records the traffic
    Given a connection for common name "vpn-alice-1" is active
    And OpenVPN reports the client "vpn-alice-1" disconnecting after 4096 bytes received and 2048 bytes sent
    When OpenVPN runs the disconnect hook
    Then the hook should exit with code 0
    And the connection of "vpn-alice-1" should be closed with 4096 bytes received and 2048 bytes sent

  Scenario: Renegotiation of a valid certificate keeps the client connected
    Given a certificate with common name "vpn-alice-1" is valid
    And OpenVPN reports the client "vpn-alice-1" from "203.0.113.7" with VPN address "10.8.0.6"
    When OpenVPN runs the renegotiation hook at depth 0
    Then the hook should exit with code 0
    And the client should not be killed

  Scenario: Renegotiation of a revoked certificate kills the client
    Given a certificate with common name "vpn-bob-1" is revoked
    And OpenVPN reports the client "vpn-bob-1" from "203.0.113.8" on port "51820"
    When OpenVPN runs the renegotiation hook at depth 0
    Then the hook should exit with code 1
    And the client "203.0.113.8:51820" should be killed

  Scenario: Certificates of the CA chain are not checked
    Given OpenVPN reports the client "vpn-ghost-1" from "203.0.113.10" on port "51820"
    When OpenVPN runs the renegotiation hook at depth 1
    Then the hook should exit with code 0
    And the client should not be killed

  Scenario: The access token is requested with client credentials
    Given the OAuth2 server issues the token "fresh-token" valid for 300 seconds
    And there is no cached token
    When the hook requests an access token
    Then the token should be "fresh-token"
    And the OAuth2 server should have received the "client_credentials" grant for scope "vpn:server"
    And the token should be cached

  Scenario: A cached token is reused
    Given there is a cached token "cached-token" valid for 300 seconds
    When the hook requests an access token
    Then the token should be "cached-token"
    And the OAuth2 server should not have been called

  Scenario: Prefix lengths are converted to netmasks
    Then the netmask for prefix 24 should be "255.255.255.0"
    And the netmask for prefix 16 should be "255.255.0.0"
    And the netmask for prefix 8 should be "255.0.0.0"
