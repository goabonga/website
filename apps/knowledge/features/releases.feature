Feature: MCP releases and downloads
  As a user of the Knowledge MCP
  I want to list and download its releases
  So that I can install the executable for my platform

  Background:
    Given the releases data layer is in memory
    And the GitHub webhook secret is "gh-secret"

  Scenario: A published GitHub release is imported
    When GitHub sends a signed "published" event for release "v1.2.0" with the assets
      | name                          | size |
      | knowledge-mcp-linux-x86_64    | 1000 |
      | knowledge-mcp-darwin-arm64    | 2000 |
      | knowledge-mcp-windows-x86_64.exe | 3000 |
      | checksums.txt                 | 10   |
    Then the response status code should be 200
    And the response JSON "release.version" should be "1.2.0"
    And the response JSON "release.status" should be "published"
    And the release "1.2.0" should have the platforms "linux-x86_64, macos-arm64, windows-x86_64"

  Scenario: An edited release updates the existing one
    Given the release "1.2.0" was imported from GitHub
    When GitHub sends a signed "edited" event for release "v1.2.0" with the notes "Fixed a bug"
    Then the response status code should be 200
    And the release "1.2.0" should have the notes "Fixed a bug"
    And there should be 1 release

  Scenario: A draft release is stored but not listed
    When GitHub sends a signed "published" event for a draft release "v2.0.0"
    Then the response status code should be 200
    And the response JSON "release.status" should be "draft"
    When I send a GET request to "/api/v1/mcp/releases"
    Then the response should be a list of 0 items

  Scenario: Events other than releases are ignored
    When GitHub sends a signed "push" event
    Then the response status code should be 200
    And the response JSON "status" should be "ignored"

  Scenario: Release actions other than publication are ignored
    When GitHub sends a signed "deleted" event for release "v1.2.0" with the assets
      | name                       | size |
      | knowledge-mcp-linux-x86_64 | 1000 |
    Then the response JSON "status" should be "ignored"
    And there should be 0 release

  Scenario: A bad signature is rejected
    When GitHub sends an event signed with the wrong secret
    Then the response status code should be 401

  Scenario: A missing signature is rejected
    When GitHub sends an unsigned event
    Then the response status code should be 401

  Scenario: A malformed release payload is rejected
    When GitHub sends a signed release payload that is not valid
    Then the response status code should be 400

  Scenario: List published releases, newest first
    Given the release "1.0.0" published on "2026-01-01T00:00:00Z" for "linux-x86_64"
    And the release "1.1.0" published on "2026-02-01T00:00:00Z" for "linux-x86_64"
    When I send a GET request to "/api/v1/mcp/releases"
    Then the response status code should be 200
    And the response JSON "0.version" should be "1.1.0"
    And the response JSON "1.version" should be "1.0.0"

  Scenario: Get the latest release
    Given the release "1.0.0" published on "2026-01-01T00:00:00Z" for "linux-x86_64"
    And the release "1.1.0" published on "2026-02-01T00:00:00Z" for "linux-x86_64,macos-arm64"
    When I send a GET request to "/api/v1/mcp/releases/latest"
    Then the response status code should be 200
    And the response JSON "version" should be "1.1.0"
    And the response JSON "assets.1.platform" should be "macos-arm64"

  Scenario: Get a release by version with or without the v prefix
    Given the release "1.0.0" published on "2026-01-01T00:00:00Z" for "linux-x86_64"
    When I send a GET request to "/api/v1/mcp/releases/v1.0.0"
    Then the response status code should be 200
    And the response JSON "version" should be "1.0.0"

  Scenario: An unknown release is not found
    When I send a GET request to "/api/v1/mcp/releases/9.9.9"
    Then the response status code should be 404

  Scenario: Downloading redirects to the asset and counts the download
    Given the release "1.0.0" published on "2026-01-01T00:00:00Z" for "linux-x86_64"
    When I send a GET request to "/api/v1/mcp/download/1.0.0/linux-x86_64"
    Then the response status code should be 302
    And the redirect location should be "https://downloads.example.test/1.0.0/linux-x86_64"
    And the asset "linux-x86_64" of release "1.0.0" should have 1 download

  Scenario: Downloading the latest release for a platform
    Given the release "1.0.0" published on "2026-01-01T00:00:00Z" for "linux-x86_64"
    And the release "1.1.0" published on "2026-02-01T00:00:00Z" for "linux-x86_64"
    When I send a GET request to "/api/v1/mcp/download/latest/linux-x86_64"
    Then the response status code should be 302
    And the redirect location should be "https://downloads.example.test/1.1.0/linux-x86_64"

  Scenario: An unknown platform is rejected
    When I send a GET request to "/api/v1/mcp/download/1.0.0/amiga"
    Then the response status code should be 400

  Scenario: A platform without asset is not found
    Given the release "1.0.0" published on "2026-01-01T00:00:00Z" for "linux-x86_64"
    When I send a GET request to "/api/v1/mcp/download/1.0.0/macos-arm64"
    Then the response status code should be 404
