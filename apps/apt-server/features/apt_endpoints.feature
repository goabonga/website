Feature: APT client endpoints
  apt clients read dists/ and pool/ over HTTP. Anonymous clients get the public
  components, authenticated clients use HTTP Basic with a personal access
  token as the password, and downloads are handed over to nginx.

  Background:
    Given the repository serves components "main,private" of which "main" is public
    And the auth service knows access token "tok-alice" for user "alice"
    And the auth service knows access token "tok-bob" for user "bob"
    And a catalog with these indexed packages
      | name  | owner | visibility | component |
      | tool  | alice | public     | main      |
      | draft | alice | private    | main      |
      | vault | alice | private    | private   |

  @database
  Scenario: Anonymous clients fetch the public Packages index
    When I request "/dists/stable/main/binary-amd64/Packages"
    Then the response status is 200
    And the response body contains "Package: tool"
    And the response body does not contain "Package: draft"

  @database
  Scenario: Release is served to anonymous clients
    When I request "/dists/stable/Release"
    Then the response status is 200
    And the response body contains "Components: main"

  @database
  Scenario: Private components ask for credentials
    When I request "/dists/stable/private/binary-amd64/Packages"
    Then the response status is 401
    And the response header "WWW-Authenticate" starts with "Basic"

  @database
  Scenario: A personal access token opens the private component
    When I request "/dists/stable/private/binary-amd64/Packages" with access token "tok-alice"
    Then the response status is 200
    And the response body contains "Package: vault"

  @database
  Scenario: An unknown access token is refused
    When I request "/dists/stable/main/binary-amd64/Packages" with access token "tok-evil"
    Then the response status is 401

  @database
  Scenario: Public packages are downloaded through nginx
    When I request "/pool/main/t/tool/tool_1.0_amd64.deb"
    Then the response status is 200
    And the response header "X-Accel-Redirect" starts with "/_internal/pool/main/t/tool"

  @database
  Scenario: Private packages are hidden from other users
    When I request "/pool/main/d/draft/draft_1.0_amd64.deb" with access token "tok-bob"
    Then the response status is 404

  @database
  Scenario: Owners download their private packages
    When I request "/pool/main/d/draft/draft_1.0_amd64.deb" with access token "tok-alice"
    Then the response status is 200

  @database
  Scenario: Unknown suites are not found
    When I request "/dists/unknown/Release"
    Then the response status is 404

  @database
  Scenario: The public key is not available without a signing key
    When I request "/pubkey.gpg"
    Then the response status is 404
