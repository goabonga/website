@browser
Feature: Workspace members and invitations pages in a browser
  As an administrator of a workspace
  I want to invite people and manage the members
  So that my team can work together in the web application

  Background:
    Given a user "Alice" who holds every knowledge scope
    And "Alice" owns the workspace "Acme" on the "pro" plan

  Scenario: The members page lists the team and offers to invite
    Given a user "Bob" who holds every knowledge scope
    And "Bob" is a member of the workspace "Acme" on the "pro" plan
    And I have signed in as "Alice" through the identity provider
    When I click "Members"
    Then the URL should be "/tenants/members"
    And the sidebar item "Members" should be the active one
    And I should see "Members (2)"
    And I should see "bob@example.test"
    When I click "Invite Member"
    Then the URL should be "/tenants/invite"
    And the sidebar item "Members" should be the active one

  Scenario: An invitation is sent by email and listed as pending
    Given I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/invite"
    And I fill "Email Address" with "carol@example.test"
    And I select "Admin - Can manage members and organization settings" from "role"
    And I click "Send Invitation"
    Then the URL should be "/organizations/members"
    And I should see "Pending Invitations (1)"
    And I should see "carol@example.test"
    And "carol@example.test" received an invitation to the workspace "Acme" as "admin"

  Scenario: The same person cannot be invited twice at once
    Given "carol@example.test" has a pending invitation to the workspace "Acme"
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/invite"
    And I fill "Email Address" with "carol@example.test"
    And I click "Send Invitation"
    Then I should see "An invitation for carol@example.test is already pending."
    And no invitation email was sent

  Scenario: An invitation is resent or revoked
    Given "carol@example.test" has a pending invitation to the workspace "Acme"
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/members"
    And I click "Resend"
    Then "carol@example.test" received 1 invitation email
    When I click "Revoke"
    Then I should not see "Pending Invitations"
    When I open the invitation link of "carol@example.test"
    Then I should see "This invitation has been revoked"

  Scenario: An invitee follows the link of the email, signs in and joins
    Given a user "Carol" who holds every knowledge scope
    And I have signed in as "Alice" through the identity provider
    And I invite "carol@example.test" as "member" from the members page
    And I sign out
    When I open the invitation link sent to "carol@example.test"
    Then I should see "You've been invited!"
    And I should see "Acme"
    When I click "Sign In to Accept"
    And I sign in as "Carol" at the identity provider
    Then the URL should contain "/tenants/invites/"
    And I should see "Logged in as"
    When I click "Accept Invitation"
    Then the URL should be "/dashboard"
    And the workspace "Acme" should have 2 members
    And the dashboard should show the plan "Pro"

  Scenario: An invitee without account is offered to sign up
    Given "dave@example.test" has a pending invitation to the workspace "Acme"
    When I open the invitation link of "dave@example.test"
    And I click "Create an Account"
    Then the URL should contain "/auth/signup"

  Scenario: An unknown invitation is reported
    When I navigate to "/tenants/invites/not-a-token"
    Then I should see "Invitation not found"
    When I click "Go to Home"
    Then the URL should be "/"

  Scenario: An expired invitation is reported
    Given "erin@example.test" has an expired invitation to the workspace "Acme"
    When I open the invitation link of "erin@example.test"
    Then I should see "This invitation has expired"

  Scenario: The role of a member is changed and the member is removed
    Given a user "Bob" who holds every knowledge scope
    And "Bob" is a member of the workspace "Acme" on the "pro" plan
    And the browser accepts the confirmation dialogs
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/members"
    And I select "Admin" from "role"
    Then "Bob" should have the role "admin" in the workspace "Acme"
    When I click "Remove"
    Then I should see "Members (1)"
    And the workspace "Acme" should have 1 member

  Scenario: A regular member cannot manage the team
    Given a user "Bob" who holds every knowledge scope
    And "Bob" is a member of the workspace "Acme" on the "pro" plan
    And I have signed in as "Bob" through the identity provider
    When I navigate to "/tenants/members"
    Then I should see "You don't have permission to access this resource."
    When I navigate to "/tenants/invite"
    Then I should see "You don't have permission to access this resource."

  Scenario: The members pages only lead to pages that exist
    Given "carol@example.test" has a pending invitation to the workspace "Acme"
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/members"
    Then every link of the page leads to a page of the application
    When I navigate to "/tenants/invite"
    Then every link of the page leads to a page of the application
    When I navigate to "/dashboard"
    Then every link of the page leads to a page of the application
    When I navigate to "/auth/logout"
    And I open the invitation link of "carol@example.test"
    Then every link of the page leads to a page of the application
