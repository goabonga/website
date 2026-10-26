Feature: Workspace members and invitations
  As an administrator of a workspace
  I want to invite people and manage their roles
  So that the right users work in the workspace

  Background:
    Given the workspace database is in memory
    And invitation emails are queued in memory

  Scenario: Administrators see the members and pending invitations
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And "bob@example.test" is a member of the workspace with the role "member"
    And "carol@example.test" has a pending invitation
    When I open "/organizations/members"
    Then the response status code should be 200
    And the page should say "bob@example.test"
    And the page should say "carol@example.test"

  Scenario: Regular members cannot see the member list
    Given I am a regular member of the workspace "Acme" on the "pro" plan
    When I open "/organizations/members"
    Then the response status code should be 403

  Scenario: Inviting someone stores an invitation and queues the email
    Given I am the owner of the workspace "Acme" on the "pro" plan
    When I invite "Dave@Example.test" as "admin"
    Then the response status code should be 302
    And I should be redirected to "/organizations/members"
    And the workspace should hold a pending "admin" invitation for "dave@example.test"
    And an invitation email should be queued for "dave@example.test" mentioning the workspace "Acme"

  Scenario: An administrator cannot invite an owner
    Given I am an administrator of the workspace "Acme" on the "pro" plan
    When I invite "eve@example.test" as "owner"
    Then the workspace should hold a pending "admin" invitation for "eve@example.test"

  Scenario: A pending invitation is not duplicated
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And "carol@example.test" has a pending invitation
    When I invite "carol@example.test" as "member"
    Then the response status code should be 200
    And the page should say "already pending"
    And no invitation email should be queued

  Scenario: Resending an invitation queues the email again
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And "carol@example.test" has a pending invitation
    When I resend the invitation of "carol@example.test"
    Then the response status code should be 302
    And an invitation email should be queued for "carol@example.test" mentioning the workspace "Acme"

  Scenario: Revoking an invitation
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And "carol@example.test" has a pending invitation
    When I revoke the invitation of "carol@example.test"
    Then the invitation of "carol@example.test" should be "revoked"

  Scenario: Changing a member's role
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And "bob@example.test" is a member of the workspace with the role "member"
    When I change the role of "bob@example.test" to "admin"
    Then "bob@example.test" should have the role "admin"

  Scenario: An administrator cannot promote someone to owner
    Given I am an administrator of the workspace "Acme" on the "pro" plan
    And "bob@example.test" is a member of the workspace with the role "member"
    When I change the role of "bob@example.test" to "owner"
    Then "bob@example.test" should have the role "admin"

  Scenario: Nobody can change their own role
    Given I am the owner of the workspace "Acme" on the "pro" plan
    When I change my own role to "member"
    Then I should still be an "owner"

  Scenario: Removing a member
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And "bob@example.test" is a member of the workspace with the role "member"
    When I remove "bob@example.test" from the workspace
    Then "bob@example.test" should no longer be a member

  Scenario: An administrator cannot remove the owner
    Given I am an administrator of the workspace "Acme" on the "pro" plan
    And "olivia@example.test" is a member of the workspace with the role "owner"
    When I remove "olivia@example.test" from the workspace
    Then "olivia@example.test" should have the role "owner"

  Scenario: A pending invitation can be viewed by anyone
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And "carol@example.test" has a pending invitation
    When a visitor opens the invitation of "carol@example.test"
    Then the response status code should be 200
    And the page should say "Acme"

  Scenario: A revoked invitation is reported
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And "carol@example.test" has a pending invitation
    And the invitation of "carol@example.test" is revoked
    When a visitor opens the invitation of "carol@example.test"
    Then the page should say "This invitation has been revoked"

  Scenario: An expired invitation is reported and marked
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And "carol@example.test" has an expired invitation
    When a visitor opens the invitation of "carol@example.test"
    Then the page should say "This invitation has expired"
    And the invitation of "carol@example.test" should be "expired"

  Scenario: An unknown invitation is reported
    When a visitor opens the invitation token "nope"
    Then the page should say "Invitation not found"

  Scenario: Accepting an invitation requires signing in
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And "carol@example.test" has a pending invitation
    When a visitor accepts the invitation of "carol@example.test"
    Then the response status code should be 302
    And I should be redirected to a URL starting with "/auth/login?redirect=/organizations/invites/"

  Scenario: A signed-in user accepts an invitation
    Given I am the owner of the workspace "Acme" on the "pro" plan
    And "carol@example.test" has a pending invitation with the role "admin"
    When the user "dddddddd-dddd-dddd-dddd-dddddddddddd" accepts the invitation of "carol@example.test"
    Then the response status code should be 302
    And I should be redirected to "/dashboard"
    And the user "dddddddd-dddd-dddd-dddd-dddddddddddd" should be an "admin" of the workspace
    And the invitation of "carol@example.test" should be "accepted"
