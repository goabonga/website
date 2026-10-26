Feature: APT index rendering
  Packages and Release indexes are rendered from the catalog and filtered
  to what the caller may see, so a package never leaks into an index the
  caller could not download from.

  Background:
    Given the repository serves components "main,private" of which "main" is public
    And a catalog with these indexed packages
      | name    | owner | visibility | component |
      | tool    | alice | public     | main      |
      | draft   | alice | private    | main      |
      | vault   | alice | private    | private   |

  @database
  Scenario: Anonymous callers get an index of public packages
    When an anonymous caller fetches the "main" Packages index
    Then the index lists "tool"
    And the index does not list "draft"

  @database
  Scenario: Owners see their private packages in the index
    When the caller "alice" fetches the "main" Packages index
    Then the index lists "tool"
    And the index lists "draft"

  @database
  Scenario: Index entries carry the pool location and checksums
    When an anonymous caller fetches the "main" Packages index
    Then the index entry for "tool" has "Filename: pool/main/t/tool/tool_1.0_amd64.deb"
    And the index entry for "tool" has a "SHA256" checksum

  @database
  Scenario: The compressed index matches the plain index
    When an anonymous caller fetches the "main" Packages index
    Then the compressed index decompresses to the same content

  @database
  Scenario: A newly added package appears once the cache is invalidated
    Given an anonymous caller fetched the "main" Packages index
    When a public package "late" is added to the catalog
    And the cached indexes are invalidated
    And an anonymous caller fetches the "main" Packages index
    Then the index lists "late"

  @database
  Scenario: Release for anonymous callers hides private components
    When an anonymous caller fetches the Release file
    Then the Release lists component "main"
    And the Release does not mention "private/"

  @database
  Scenario: Release for the owner exposes components holding visible packages
    When the caller "alice" fetches the Release file
    Then the Release lists component "private"
    And the Release references "main/binary-amd64/Packages.gz"
