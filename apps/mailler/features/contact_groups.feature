Feature: Contact Groups
  Manage contact groups with CRUD and group membership.

  Background:
    Given I am authenticated

  # ── List ──────────────────────────────────────────────────────────────────

  Scenario: List contact groups when none exist
    When I send a GET to "/api/v1/contact-groups"
    Then the response status should be 200
    And the response JSON "total" should be "0"

  Scenario: List contact groups with search
    When I send a POST to "/api/v1/contact-groups" with
      """
      {
        "slug": "newsletter-subs",
        "name": "Newsletter Subscribers",
        "description": "Weekly newsletter recipients"
      }
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/contact-groups?search=newsletter"
    Then the response status should be 200
    And the response JSON "total" should be "1"

  # ── Create ────────────────────────────────────────────────────────────────

  Scenario: Create a contact group
    When I send a POST to "/api/v1/contact-groups" with
      """
      {
        "slug": "vip-customers",
        "name": "VIP Customers",
        "description": "High-value customers"
      }
      """
    Then the response status should be 201
    And the response JSON "slug" should be "vip-customers"
    And the response JSON "name" should be "VIP Customers"
    And the response JSON "member_count" should be "0"
    And the response JSON should contain "id"

  Scenario: Create dynamic contact group
    When I send a POST to "/api/v1/contact-groups" with
      """
      {
        "slug": "active-users",
        "name": "Active Users",
        "is_dynamic": true,
        "filter_criteria": {"status": "active"}
      }
      """
    Then the response status should be 201
    And the response JSON "is_dynamic" should be true

  Scenario: Create group with duplicate slug fails
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "dupe-group", "name": "First"}
      """
    Then the response status should be 201
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "dupe-group", "name": "Second"}
      """
    Then the response status should be 409

  Scenario: Create group with invalid slug fails
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "Invalid Slug!", "name": "Bad"}
      """
    Then the response status should be 422

  # ── Get ───────────────────────────────────────────────────────────────────

  Scenario: Get contact group by ID
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "get-by-id", "name": "Get By ID"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a GET to "/api/v1/contact-groups/{group_id}"
    Then the response status should be 200
    And the response JSON "slug" should be "get-by-id"

  Scenario: Get contact group by slug
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "slug-lookup", "name": "Slug Lookup"}
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/contact-groups/by-slug/slug-lookup"
    Then the response status should be 200
    And the response JSON "name" should be "Slug Lookup"

  Scenario: Get group returns 404 for unknown ID
    When I send a GET to "/api/v1/contact-groups/99999"
    Then the response status should be 404

  Scenario: Get group by slug returns 404
    When I send a GET to "/api/v1/contact-groups/by-slug/nonexistent"
    Then the response status should be 404

  # ── Update ────────────────────────────────────────────────────────────────

  Scenario: Update a contact group
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "updatable-group", "name": "Original"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a PUT to "/api/v1/contact-groups/{group_id}" with
      """
      {"name": "Updated Group Name", "description": "Now described"}
      """
    Then the response status should be 200
    And the response JSON "name" should be "Updated Group Name"

  Scenario: Update non-existent group returns 404
    When I send a PUT to "/api/v1/contact-groups/99999" with
      """
      {"name": "Ghost"}
      """
    Then the response status should be 404

  # ── Delete ────────────────────────────────────────────────────────────────

  Scenario: Delete a contact group
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "deletable-group", "name": "Deletable"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a DELETE to "/api/v1/contact-groups/{group_id}"
    Then the response status should be 204
    When I send a GET to "/api/v1/contact-groups/{group_id}"
    Then the response status should be 404

  Scenario: Delete non-existent group returns 404
    When I send a DELETE to "/api/v1/contact-groups/99999"
    Then the response status should be 404

  # ── Membership ────────────────────────────────────────────────────────────

  Scenario: Add contacts to a group
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "members-group", "name": "Members Group"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "member1@example.com", "first_name": "Member One"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a POST to "/api/v1/contact-groups/{group_id}/contacts" with
      """
      {"contact_ids": ["{contact_id}"]}
      """
    Then the response status should be 200
    And the response JSON should contain "added"

  Scenario: List contacts in a group
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "list-members", "name": "List Members"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a GET to "/api/v1/contact-groups/{group_id}/contacts"
    Then the response status should be 200
    And the response JSON should contain "items"
    And the response JSON should contain "total"

  Scenario: List available contacts for a group
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "available-test", "name": "Available Test"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a GET to "/api/v1/contact-groups/{group_id}/available-contacts"
    Then the response status should be 200
    And the response JSON should contain "items"

  Scenario: Remove contacts from a group
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "remove-test", "name": "Remove Test"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "removable@example.com"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a POST to "/api/v1/contact-groups/{group_id}/contacts" with
      """
      {"contact_ids": ["{contact_id}"]}
      """
    Then the response status should be 200
    When I send a DELETE to "/api/v1/contact-groups/{group_id}/contacts" with
      """
      {"contact_ids": ["{contact_id}"]}
      """
    Then the response status should be 200
    And the response JSON should contain "removed"

  # ── Auth ──────────────────────────────────────────────────────────────────

  Scenario: Contact group endpoints require authentication
    Given I am not authenticated
    When I send a GET to "/api/v1/contact-groups"
    Then the response status should be 401

  # ── Scopes and membership details ─────────────────────────────────────────

  Scenario: A read-only token cannot create groups
    Given I am authenticated with scopes "mailler:read"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "forbidden", "name": "Forbidden"}
      """
    Then the response status should be 403

  Scenario: Adding a contact twice skips it the second time
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "twice", "name": "Twice"}
      """
    Then the response status should be 201
    And I store the response "id" as "group_id"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "twice@example.com"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a POST to "/api/v1/contact-groups/{group_id}/contacts" with
      """
      {"contact_ids": ["{contact_id}"]}
      """
    Then the response status should be 200
    And the response JSON "added" should be "1"
    When I send a POST to "/api/v1/contact-groups/{group_id}/contacts" with
      """
      {"contact_ids": ["{contact_id}"]}
      """
    Then the response status should be 200
    And the response JSON "added" should be "0"
    And the response JSON "skipped" should be "1"

  # ── Isolation between clients ─────────────────────────────────────────────

  Scenario: The same group slug can be used by two clients
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "vip", "name": "One"}
      """
    Then the response status should be 201
    And the response JSON "client_id" should be "app-one"
    Given I am authenticated as client "app-two" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "vip", "name": "Two"}
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/contact-groups/by-slug/vip"
    Then the response JSON "name" should be "Two"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "vip", "name": "Again"}
      """
    Then the response status should be 409

  Scenario: A client neither lists, reads, edits, fills nor deletes the groups of another client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "private", "name": "Private"}
      """
    Then the response status should be 201
    And I store the response "id" as "group"
    Given I am authenticated as client "app-two" with scopes "mailler:read mailler:write"
    When I send a GET to "/api/v1/contact-groups"
    Then the response JSON "total" should be "0"
    When I send a GET to "/api/v1/contact-groups/{group}"
    Then the response status should be 404
    When I send a GET to "/api/v1/contact-groups/by-slug/private"
    Then the response status should be 404
    When I send a PUT to "/api/v1/contact-groups/{group}" with
      """
      {"name": "Hijacked"}
      """
    Then the response status should be 404
    When I send a GET to "/api/v1/contact-groups/{group}/contacts"
    Then the response status should be 404
    When I send a GET to "/api/v1/contact-groups/{group}/available-contacts"
    Then the response status should be 404
    When I send a DELETE to "/api/v1/contact-groups/{group}"
    Then the response status should be 404

  Scenario: Only the contacts of the client can join its groups
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "mine@example.com"}
      """
    Then I store the response "id" as "mine"
    Given I am authenticated as client "app-two" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "theirs@example.com"}
      """
    Then I store the response "id" as "theirs"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "other-team", "name": "Other team"}
      """
    Then I store the response "id" as "other_group"
    When I send a POST to "/api/v1/contact-groups/{other_group}/contacts" with
      """
      {"contact_ids": ["{mine}", "{theirs}"]}
      """
    Then the response status should be 200
    And the response JSON "added" should be "1"
    And the response JSON "skipped" should be "1"
    When I send a GET to "/api/v1/contact-groups/{other_group}/available-contacts"
    Then the response JSON "total" should be "0"

  Scenario: A client cannot name another client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contact-groups?client_id=app-two" with
      """
      {"slug": "forged", "name": "Forged"}
      """
    Then the response status should be 403
    When I send a GET to "/api/v1/contact-groups?client_id=app-two"
    Then the response status should be 403

  Scenario: An administrator creates groups for a client
    Given I am authenticated as client "ops" with scopes "mailler:read mailler:write mailler:admin"
    When I send a POST to "/api/v1/contact-groups?client_id=app-one" with
      """
      {"slug": "seeded", "name": "Seeded"}
      """
    Then the response status should be 201
    And the response JSON "client_id" should be "app-one"
    When I send a GET to "/api/v1/contact-groups"
    Then the response JSON "total" should be "1"
