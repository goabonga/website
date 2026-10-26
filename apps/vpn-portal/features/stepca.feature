Feature: Step-CA root certificate
  As a VPN user
  I want to download the root certificate of the certificate authority
  So that my client can trust the certificates issued by the portal

  Scenario: Get root CA certificate successfully
    Given I am authenticated with "vpn:connect" scope
    And the Step-CA server will return the root CA
    When I send a GET request to "/api/v1/vpn/ca"
    Then the response status code should be 200
    And the response body should include "ca_certificate"
    And the response body should include "fingerprint"

  Scenario: Get root CA certificate when Step-CA is unavailable
    Given I am authenticated with "vpn:connect" scope
    And the Step-CA server will fail to return the root CA
    When I send a GET request to "/api/v1/vpn/ca"
    Then the response status code should be 502
    And the response body should include "detail"

  Scenario: Get root CA certificate without authentication
    When I send a GET request to "/api/v1/vpn/ca"
    Then the response status code should be 401

  Scenario: Get root CA certificate with insufficient scope
    Given I am authenticated with "openid" scope
    When I send a GET request to "/api/v1/vpn/ca"
    Then the response status code should be 403

  Scenario: The fingerprint is computed from the local root certificate
    Given a local root CA certificate
    When the client computes the root fingerprint
    Then the fingerprint should be 64 hexadecimal characters

  Scenario: A missing local root certificate is reported
    Given no local root CA certificate
    When the client computes the root fingerprint
    Then the client should report that the CA certificate is not found
