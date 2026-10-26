Feature: Access control rules
  Component visibility and OAuth2 scopes decide who may read, write and
  reindex before any package level rule applies.

  Background:
    Given the repository serves components "main,private"
    And the public components are "main"

  Scenario: Anonymous callers only see public components
    Then component "main" is public
    And component "private" is known but not public
    And component "rogue" is unknown

  Scenario: Administrators may do everything
    Given a caller with scopes "apt:admin"
    Then the caller may read
    And the caller may write to component "private"
    And the caller may reindex

  Scenario: A global write scope covers every component
    Given a caller with scopes "apt:write"
    Then the caller may write to component "main"
    And the caller may write to component "private"
    And the caller may not reindex

  Scenario: A component write scope is limited to that component
    Given a caller with scopes "apt:write:private"
    Then the caller may write to component "private"
    And the caller may not write to component "main"
    And the caller may read

  Scenario: A read scope does not allow uploads
    Given a caller with scopes "apt:read"
    Then the caller may read
    And the caller may not write to component "main"

  Scenario: A caller without apt scopes is treated as anonymous
    Given a caller with scopes "openid profile"
    Then the caller may not read
