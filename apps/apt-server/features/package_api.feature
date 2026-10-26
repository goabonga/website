Feature: Package API
  Authenticated users upload .deb files, list and update their packages and
  manage who may read or write them.

  Background:
    Given the repository serves components "main,private" of which "main" is public

  @database
  Scenario: A writer uploads a package
    Given I am logged in as "alice" with scopes "apt:write"
    When I upload the package "demo" version "1.0" to component "main"
    Then the response status is 201
    And the JSON field "name" is "demo"
    And the JSON field "owner_id" is "alice"
    And the package file exists in the pool

  @database
  Scenario: A reader cannot upload
    Given I am logged in as "bob" with scopes "apt:read"
    When I upload the package "demo" version "1.0" to component "main"
    Then the response status is 403

  @database
  Scenario: A component scoped writer is limited to its component
    Given I am logged in as "ci" with scopes "apt:write:private"
    When I upload the package "demo" version "1.0" to component "main"
    Then the response status is 403
    When I upload the package "demo" version "1.0" to component "private"
    Then the response status is 201

  @database
  Scenario: Uploading the same version twice is a conflict
    Given I am logged in as "alice" with scopes "apt:write"
    And I uploaded the package "demo" version "1.0" to component "main"
    When I upload the package "demo" version "1.0" to component "main"
    Then the response status is 409

  @database
  Scenario: A file that is not a Debian package is rejected
    Given I am logged in as "alice" with scopes "apt:write"
    When I upload a file that is not a Debian package
    Then the response status is 400

  @database
  Scenario: Private packages are only listed for their owner
    Given I am logged in as "alice" with scopes "apt:write"
    And I uploaded the package "demo" version "1.0" to component "main"
    When I list the packages
    Then the response lists 1 package
    Given I am logged in as "bob" with scopes "apt:read"
    When I list the packages
    Then the response lists 0 packages

  @database
  Scenario: Granting read access shares a package
    Given I am logged in as "alice" with scopes "apt:write"
    And I uploaded the package "demo" version "1.0" to component "main"
    When I grant "read" on the last package to user "bob"
    Then the response status is 201
    Given I am logged in as "bob" with scopes "apt:read"
    When I list the packages
    Then the response lists 1 package

  @database
  Scenario: Making a package public exposes it to everyone
    Given I am logged in as "alice" with scopes "apt:write"
    And I uploaded the package "demo" version "1.0" to component "main"
    When I set the visibility of the last package to "public"
    Then the response status is 200
    Given I am logged in as "bob" with scopes "apt:read"
    When I list the packages
    Then the response lists 1 package

  @database
  Scenario: Only the owner can delete a package
    Given I am logged in as "alice" with scopes "apt:write"
    And I uploaded the package "demo" version "1.0" to component "main"
    Given I am logged in as "bob" with scopes "apt:write"
    When I delete the last package
    Then the response status is 403
    Given I am logged in as "alice" with scopes "apt:write"
    When I delete the last package
    Then the response status is 204
    And the package file no longer exists in the pool

  @database
  Scenario: Only administrators can reindex
    Given I am logged in as "alice" with scopes "apt:write"
    When I trigger a reindex
    Then the response status is 403
    Given I am logged in as "root" with scopes "apt:admin"
    When I trigger a reindex
    Then the response status is 204
