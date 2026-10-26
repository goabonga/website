Feature: Collection collaborators and invitations
  As the owner of a collection
  I want to share it with other users
  So that they can read or edit it with the permission I choose

  Background:
    Given I am authenticated as user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" with scopes "collections:read collections:write"
    And the collaboration data layer is in memory
    And I own a collection "Handbook" with slug "handbook"

  Scenario: Add a collaborator
    When I add user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" as "write" collaborator of "handbook"
    Then the response status code should be 201
    And the response JSON "permission" should be "write"
    And the response JSON "user_id" should be "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

  Scenario: A user cannot add themselves as collaborator
    When I add user "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" as "read" collaborator of "handbook"
    Then the response status code should be 400

  Scenario: A collaborator cannot be added twice
    Given user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" is a "read" collaborator of "handbook"
    When I add user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" as "write" collaborator of "handbook"
    Then the response status code should be 409

  Scenario: List the collaborators of a collection
    Given user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" is a "read" collaborator of "handbook"
    And user "cccccccc-cccc-cccc-cccc-cccccccccccc" is a "write" collaborator of "handbook"
    When I list the collaborators of "handbook"
    Then the response status code should be 200
    And the response should be a list of 2 items

  Scenario: Change the permission of a collaborator
    Given user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" is a "read" collaborator of "handbook"
    When I change the permission of user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" on "handbook" to "admin"
    Then the response status code should be 200
    And the response JSON "permission" should be "admin"

  Scenario: Remove a collaborator
    Given user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" is a "read" collaborator of "handbook"
    When I remove user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" from "handbook"
    Then the response status code should be 204
    When I list the collaborators of "handbook"
    Then the response should be a list of 0 items

  Scenario: A read-only collaborator cannot add collaborators
    Given user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" is a "read" collaborator of "handbook"
    And I am authenticated as user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" with scopes "collections:read collections:write"
    When I add user "cccccccc-cccc-cccc-cccc-cccccccccccc" as "read" collaborator of "handbook"
    Then the response status code should be 403

  Scenario: A collaborator can leave a collection
    Given user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" is a "read" collaborator of "handbook"
    And I am authenticated as user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" with scopes "collections:read collections:write"
    When I remove user "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" from "handbook"
    Then the response status code should be 204

  Scenario: Collaborators of an unknown collection are not found
    When I send a GET request to "/api/v1/collections/11111111-1111-1111-1111-111111111111/collaborators"
    Then the response status code should be 404

  Scenario: Create an invitation
    When I invite "Alice@Example.com" to "handbook" with permission "write"
    Then the response status code should be 201
    And the response JSON "email" should be "alice@example.com"
    And the response JSON "status" should be "pending"
    And the response JSON "permission" should be "write"

  Scenario: A pending invitation cannot be duplicated
    Given "alice@example.com" is invited to "handbook" with permission "read"
    When I invite "alice@example.com" to "handbook" with permission "read"
    Then the response status code should be 409

  Scenario: An invalid email is rejected
    When I invite "not-an-email" to "handbook" with permission "read"
    Then the response status code should be 422

  Scenario: List the invitations of a collection
    Given "alice@example.com" is invited to "handbook" with permission "read"
    When I list the invitations of "handbook"
    Then the response status code should be 200
    And the response should be a list of 1 items

  Scenario: View an invitation without authentication
    Given "alice@example.com" is invited to "handbook" with permission "read"
    When I view the invitation of "alice@example.com"
    Then the response status code should be 200
    And the response JSON "collection_name" should be "Handbook"
    And the response JSON "is_valid" should be "True"

  Scenario: Accept an invitation
    Given "alice@example.com" is invited to "handbook" with permission "write"
    And I am authenticated as user "dddddddd-dddd-dddd-dddd-dddddddddddd" with scopes "collections:read"
    When I accept the invitation of "alice@example.com"
    Then the response status code should be 200
    And the response JSON "permission" should be "write"
    And user "dddddddd-dddd-dddd-dddd-dddddddddddd" should be a collaborator of "handbook"

  Scenario: A revoked invitation cannot be accepted
    Given "alice@example.com" is invited to "handbook" with permission "read"
    When I revoke the invitation of "alice@example.com" on "handbook"
    Then the response status code should be 204
    When I accept the invitation of "alice@example.com"
    Then the response status code should be 400

  Scenario: Resending an invitation issues a new token
    Given "alice@example.com" is invited to "handbook" with permission "read"
    When I resend the invitation of "alice@example.com" on "handbook"
    Then the response status code should be 200
    And the invitation of "alice@example.com" should have a new token

  Scenario: An unknown invitation token is not found
    When I send a GET request to "/api/v1/collection-invites/unknown-token"
    Then the response status code should be 404
