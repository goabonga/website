Feature: Chunked upload
  Large packages are sent in sequential chunks within an upload session and
  assembled into a regular package once every chunk has arrived.

  Background:
    Given the repository serves components "main,private" of which "main" is public

  @database
  Scenario: A package is uploaded in several chunks
    Given I am the apt caller "alice" with scopes "apt:write"
    When I start a chunked upload of the package "bigtool" version "3.1"
    And I send all the chunks in order
    And I complete the chunked upload
    Then the response status is 200
    And the JSON field "name" is "bigtool"
    And the JSON field "version" is "3.1"
    And the package file exists in the pool

  @database
  Scenario: The upload cannot be completed while chunks are missing
    Given I am the apt caller "alice" with scopes "apt:write"
    When I start a chunked upload of the package "bigtool" version "3.1"
    And I send only the first chunk
    And I complete the chunked upload
    Then the response status is 400

  @database
  Scenario: Another user cannot add chunks to my upload
    Given I am the apt caller "alice" with scopes "apt:write"
    When I start a chunked upload of the package "bigtool" version "3.1"
    And I am the apt caller "mallory" with scopes "apt:write"
    And I send only the first chunk
    Then the response status is 403

  @database
  Scenario: A cancelled upload cannot be completed
    Given I am the apt caller "alice" with scopes "apt:write"
    When I start a chunked upload of the package "bigtool" version "3.1"
    And I cancel the chunked upload
    Then the response status is 204
    When I complete the chunked upload
    Then the response status is 404

  @database
  Scenario: Callers without a write scope cannot start an upload
    Given I am the apt caller "bob" with scopes "apt:read"
    When I start a chunked upload of the package "bigtool" version "3.1"
    Then the response status is 403

  @database
  Scenario: Anonymous callers cannot start an upload
    Given I am an anonymous apt caller
    When I start a chunked upload of the package "bigtool" version "3.1"
    Then the response status is 401
