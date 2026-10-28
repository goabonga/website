Feature: Synchronisation of the system roles of the organisations
    As an operator
    I want the owner, admin and member roles of the existing organisations to follow the defaults
    So that a scope added to the defaults reaches the organisations created before it, without a migration

    Background:
        Given an empty user database
        And a verified user "owner@example.com" with the password "Sup3r!secret"
        And "owner@example.com" owns the organisation "acme"
        And the organisation "acme" was created before the admin role held "domain:read"

    Scenario: The admin role of an existing organisation receives the new scope
        When I run "auth tenant-roles sync"
        Then the command exits with 0
        And the command prints "updated organisation acme role admin (+domain:read)"
        And the "admin" role of the organisation "acme" grants "domain:read"
        And the "admin" role of the organisation "acme" does not grant "domain:write"

    Scenario: Running it again changes nothing
        Given the system roles were synchronised
        When I run "auth tenant-roles sync --json"
        Then the command exits with 0
        And the JSON report says nothing changed

    Scenario: A dry run reports the changes and applies none
        When I run "auth tenant-roles sync --dry-run"
        Then the command exits with 0
        And the command prints "would update organisation acme role admin (+domain:read)"
        And the "admin" role of the organisation "acme" does not grant "domain:read"

    Scenario: The JSON report says what each organisation received
        Given "owner@example.com" owns the organisation "beta"
        And the organisation "beta" was created before the admin role held "domain:read"
        When I run "auth tenant-roles sync --json"
        Then the command exits with 0
        And the JSON report says the organisation "acme" received "domain:read" on the role "admin"
        And the JSON report says the organisation "beta" received "domain:read" on the role "admin"

    Scenario: What an organisation customised is kept, and so are its custom roles
        Given the "admin" role of the organisation "acme" also grants "billing:read"
        And the organisation "acme" has a role "auditor" granting "members:read"
        When I run "auth tenant-roles sync"
        Then the command exits with 0
        And the "admin" role of the organisation "acme" grants "billing:read"
        And the "admin" role of the organisation "acme" grants "domain:read"
        And the "auditor" role of the organisation "acme" grants exactly "members:read"
        And the "owner" role of the organisation "acme" grants exactly "*"

    Scenario: A missing system role is created
        Given the organisation "acme" lost its "member" role
        When I run "auth tenant-roles sync"
        Then the command exits with 0
        And the command prints "created organisation acme role member with 1 scope(s)"
        And the organisation "acme" has the roles "owner, admin, member"
        And the "member" role of the organisation "acme" grants exactly "members:read"

    Scenario: The bootstrap does not change the system roles of the organisations
        Given the bootstrap was run
        When I run "auth tenant-roles sync --dry-run"
        Then the command prints "would update organisation acme role admin (+domain:read)"
        When I run "auth bootstrap"
        Then the command exits with 0
        And the "admin" role of the organisation "acme" does not grant "domain:read"
