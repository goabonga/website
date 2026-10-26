Feature: Contacts
  Manage email contacts with CRUD, bulk operations, and unsubscribe.

  Background:
    Given I am authenticated

  # ── List ──────────────────────────────────────────────────────────────────

  Scenario: List contacts when none exist
    When I send a GET to "/api/v1/contacts"
    Then the response status should be 200
    And the response JSON "total" should be "0"

  Scenario: List contacts with pagination
    When I send a GET to "/api/v1/contacts?page=1&page_size=10"
    Then the response status should be 200
    And the response JSON should contain "items"
    And the response JSON should contain "total"
    And the response JSON should contain "pages"

  Scenario: List contacts with search filter
    When I send a POST to "/api/v1/contacts" with
      """
      {
        "email": "searchme@example.com",
        "first_name": "Findable",
        "last_name": "Person"
      }
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/contacts?search=searchme"
    Then the response status should be 200
    And the response JSON "total" should be "1"

  Scenario: List contacts filtered by status
    When I send a GET to "/api/v1/contacts?status=active"
    Then the response status should be 200
    And the response JSON should contain "items"

  # ── Create ────────────────────────────────────────────────────────────────

  Scenario: Create a contact successfully
    When I send a POST to "/api/v1/contacts" with
      """
      {
        "email": "newuser@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "source": "api",
        "custom_fields": {"company": "Acme"}
      }
      """
    Then the response status should be 201
    And the response JSON "email" should be "newuser@example.com"
    And the response JSON "first_name" should be "John"
    And the response JSON "last_name" should be "Doe"
    And the response JSON "status" should be "active"
    And the response JSON should contain "id"

  Scenario: Create contact with duplicate email fails
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "duplicate@example.com", "first_name": "First"}
      """
    Then the response status should be 201
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "duplicate@example.com", "first_name": "Second"}
      """
    Then the response status should be 409

  Scenario: Create contact with invalid email fails
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "not-valid"}
      """
    Then the response status should be 422

  # ── Bulk Create ───────────────────────────────────────────────────────────

  Scenario: Bulk create contacts
    When I send a POST to "/api/v1/contacts/bulk" with
      """
      {
        "contacts": [
          {"email": "bulk1@example.com", "first_name": "Bulk One"},
          {"email": "bulk2@example.com", "first_name": "Bulk Two"},
          {"email": "bulk3@example.com", "first_name": "Bulk Three"}
        ],
        "skip_existing": true
      }
      """
    Then the response status should be 201
    And the response JSON "created" should be "3"
    And the response JSON "skipped" should be "0"

  Scenario: Bulk create skips existing contacts
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "existing@example.com", "first_name": "Existing"}
      """
    Then the response status should be 201
    When I send a POST to "/api/v1/contacts/bulk" with
      """
      {
        "contacts": [
          {"email": "existing@example.com", "first_name": "Existing"},
          {"email": "newbulk@example.com", "first_name": "New"}
        ],
        "skip_existing": true
      }
      """
    Then the response status should be 201
    And the response JSON "created" should be "1"
    And the response JSON "skipped" should be "1"

  # ── Get ───────────────────────────────────────────────────────────────────

  Scenario: Get contact by ID
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "getbyid@example.com", "first_name": "Get"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a GET to "/api/v1/contacts/{contact_id}"
    Then the response status should be 200
    And the response JSON "email" should be "getbyid@example.com"

  Scenario: Get contact by email
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "findbyemail@example.com", "first_name": "Find"}
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/contacts/by-email/findbyemail@example.com"
    Then the response status should be 200
    And the response JSON "email" should be "findbyemail@example.com"

  Scenario: Get contact returns 404 for unknown ID
    When I send a GET to "/api/v1/contacts/00000000-0000-0000-0000-000000000000"
    Then the response status should be 404

  Scenario: Get contact by email returns 404 for unknown email
    When I send a GET to "/api/v1/contacts/by-email/unknown@example.com"
    Then the response status should be 404

  # ── Update ────────────────────────────────────────────────────────────────

  Scenario: Update a contact
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "updatable@example.com", "first_name": "Original"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a PUT to "/api/v1/contacts/{contact_id}" with
      """
      {"first_name": "Updated", "last_name": "Name"}
      """
    Then the response status should be 200
    And the response JSON "first_name" should be "Updated"
    And the response JSON "last_name" should be "Name"

  Scenario: Update contact status
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "statuschange@example.com"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a PUT to "/api/v1/contacts/{contact_id}" with
      """
      {"status": "unsubscribed"}
      """
    Then the response status should be 200
    And the response JSON "status" should be "unsubscribed"

  Scenario: Update non-existent contact returns 404
    When I send a PUT to "/api/v1/contacts/00000000-0000-0000-0000-000000000000" with
      """
      {"first_name": "Ghost"}
      """
    Then the response status should be 404

  # ── Delete ────────────────────────────────────────────────────────────────

  Scenario: Delete a contact
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "deletable@example.com"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a DELETE to "/api/v1/contacts/{contact_id}"
    Then the response status should be 204
    When I send a GET to "/api/v1/contacts/{contact_id}"
    Then the response status should be 404

  Scenario: Delete non-existent contact returns 404
    When I send a DELETE to "/api/v1/contacts/00000000-0000-0000-0000-000000000000"
    Then the response status should be 404

  # ── Unsubscribe ───────────────────────────────────────────────────────────

  Scenario: Unsubscribe a contact via API
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "unsubme@example.com", "first_name": "Unsub"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a POST to "/api/v1/contacts/{contact_id}/unsubscribe"
    Then the response status should be 200
    And the response JSON "status" should be "unsubscribed"

  Scenario: Unsubscribe non-existent contact returns 404
    When I send a POST to "/api/v1/contacts/00000000-0000-0000-0000-000000000000/unsubscribe"
    Then the response status should be 404

  # ── Auth ──────────────────────────────────────────────────────────────────

  Scenario: Contact endpoints require authentication
    Given I am not authenticated
    When I send a GET to "/api/v1/contacts"
    Then the response status should be 401

  # ── Scopes ────────────────────────────────────────────────────────────────

  Scenario: A read-only token can list contacts
    Given I am authenticated with scopes "mailler:read"
    When I send a GET to "/api/v1/contacts"
    Then the response status should be 200

  Scenario: A read-only token cannot create contacts
    Given I am authenticated with scopes "mailler:read"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "forbidden@example.com"}
      """
    Then the response status should be 403

  Scenario: Unsubscribed contacts keep their record
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "leaving@example.com"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a POST to "/api/v1/contacts/{contact_id}/unsubscribe"
    Then the response status should be 200
    And the response JSON "status" should be "unsubscribed"
    When I send a GET to "/api/v1/contacts?status=unsubscribed"
    Then the response status should be 200
    And the response JSON "total" should be "1"

  # ── Isolation between clients ─────────────────────────────────────────────

  Scenario: The same address is a distinct contact for each client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "shared@example.com", "first_name": "One"}
      """
    Then the response status should be 201
    And the response JSON "client_id" should be "app-one"
    Given I am authenticated as client "app-two" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "shared@example.com", "first_name": "Two"}
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/contacts/by-email/shared@example.com"
    Then the response JSON "first_name" should be "Two"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "shared@example.com"}
      """
    Then the response status should be 409

  Scenario: A client neither lists, reads, edits, unsubscribes nor deletes the contacts of another client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "private@example.com"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact"
    Given I am authenticated as client "app-two" with scopes "mailler:read mailler:write"
    When I send a GET to "/api/v1/contacts"
    Then the response JSON "total" should be "0"
    When I send a GET to "/api/v1/contacts/{contact}"
    Then the response status should be 404
    When I send a GET to "/api/v1/contacts/by-email/private@example.com"
    Then the response status should be 404
    When I send a PUT to "/api/v1/contacts/{contact}" with
      """
      {"first_name": "Hijacked"}
      """
    Then the response status should be 404
    When I send a POST to "/api/v1/contacts/{contact}/unsubscribe"
    Then the response status should be 404
    When I send a DELETE to "/api/v1/contacts/{contact}"
    Then the response status should be 404
    Given I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/contacts/{contact}"
    Then the response status should be 200
    And the response JSON "status" should be "active"

  Scenario: Bulk creation only sees the contacts of the calling client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "a@example.com"}
      """
    Then the response status should be 201
    Given I am authenticated as client "app-two" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contacts/bulk" with
      """
      {"contacts": [{"email": "a@example.com"}, {"email": "b@example.com"}]}
      """
    Then the response status should be 201
    And the response JSON "created" should be "2"
    And the response JSON "skipped" should be "0"

  Scenario: A client cannot name another client
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contacts?client_id=app-two" with
      """
      {"email": "forged@example.com"}
      """
    Then the response status should be 403
    When I send a GET to "/api/v1/contacts?client_id=app-two"
    Then the response status should be 403

  Scenario: An administrator creates contacts for a client and sees every client
    Given I am authenticated as client "ops" with scopes "mailler:read mailler:write mailler:admin"
    When I send a POST to "/api/v1/contacts?client_id=app-one" with
      """
      {"email": "seeded@example.com"}
      """
    Then the response status should be 201
    And the response JSON "client_id" should be "app-one"
    When I send a GET to "/api/v1/contacts"
    Then the response JSON "total" should be "1"
    When I send a GET to "/api/v1/contacts?client_id=app-two"
    Then the response JSON "total" should be "0"
