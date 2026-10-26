Feature: Public Unsubscribe
  Public unsubscribe pages allowing email recipients to opt out via signed URLs.

  # ── Confirmation Page (GET) ───────────────────────────────────────────────

  Scenario: Show unsubscribe confirmation page with valid signature
    Given I am not authenticated
    And a valid unsubscribe signature for "user@example.com" of client "bdd-client"
    When I send a GET to "/api/v1/unsubscribe?email=user@example.com&client=bdd-client&sig={unsub_sig}"
    Then the response status should be 200
    And the response should contain "Unsubscribe from emails"

  Scenario: Reject unsubscribe page with invalid signature
    Given I am not authenticated
    When I send a GET to "/api/v1/unsubscribe?email=user@example.com&client=bdd-client&sig=invalidsignature"
    Then the response status should be 403
    And the response should contain "Unsubscribe failed"

  # ── Process Unsubscribe (POST) ────────────────────────────────────────────

  Scenario: Process unsubscribe for existing contact
    Given I am authenticated
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "unsub-target@example.com", "first_name": "Unsub"}
      """
    Then the response status should be 201
    Given I am not authenticated
    And a valid unsubscribe signature for "unsub-target@example.com" of client "bdd-client"
    When I send a POST to "/api/v1/unsubscribe?email=unsub-target@example.com&client=bdd-client&sig={unsub_sig}"
    Then the response status should be 200
    And the response should contain "Successfully unsubscribed"

  Scenario: Process unsubscribe for unknown contact still shows success
    Given I am not authenticated
    And a valid unsubscribe signature for "unknown@example.com" of client "bdd-client"
    When I send a POST to "/api/v1/unsubscribe?email=unknown@example.com&client=bdd-client&sig={unsub_sig}"
    Then the response status should be 200
    And the response should contain "Successfully unsubscribed"

  Scenario: Process unsubscribe with invalid signature is rejected
    Given I am not authenticated
    When I send a POST to "/api/v1/unsubscribe?email=user@example.com&client=bdd-client&sig=badsig"
    Then the response status should be 403
    And the response should contain "Unsubscribe failed"

  Scenario: Unsubscribe already unsubscribed contact shows success
    Given I am authenticated
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "already-unsub@example.com"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    When I send a PUT to "/api/v1/contacts/{contact_id}" with
      """
      {"status": "unsubscribed"}
      """
    Then the response status should be 200
    Given I am not authenticated
    And a valid unsubscribe signature for "already-unsub@example.com" of client "bdd-client"
    When I send a POST to "/api/v1/unsubscribe?email=already-unsub@example.com&client=bdd-client&sig={unsub_sig}"
    Then the response status should be 200
    And the response should contain "Successfully unsubscribed"

  # ── Effects and failure modes ─────────────────────────────────────────────

  Scenario: Unsubscribing changes the status of the contact
    Given I am authenticated
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "status-check@example.com"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    Given I am not authenticated
    And a valid unsubscribe signature for "status-check@example.com" of client "bdd-client"
    When I send a POST to "/api/v1/unsubscribe?email=status-check@example.com&client=bdd-client&sig={unsub_sig}"
    Then the response status should be 200
    Given I am authenticated
    When I send a GET to "/api/v1/contacts/{contact_id}"
    Then the response status should be 200
    And the response JSON "status" should be "unsubscribed"

  Scenario: An invalid signature leaves the contact untouched
    Given I am authenticated
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "untouched@example.com"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    Given I am not authenticated
    When I send a POST to "/api/v1/unsubscribe?email=untouched@example.com&client=bdd-client&sig=forged"
    Then the response status should be 403
    Given I am authenticated
    When I send a GET to "/api/v1/contacts/{contact_id}"
    Then the response status should be 200
    And the response JSON "status" should be "active"

  Scenario: A signature for another address is rejected
    Given I am not authenticated
    And a valid unsubscribe signature for "alice@example.com" of client "bdd-client"
    When I send a GET to "/api/v1/unsubscribe?email=bob@example.com&client=bdd-client&sig={unsub_sig}"
    Then the response status should be 403

  Scenario: Unsubscribing is refused when no signing secret is configured
    Given I am not authenticated
    And the setting "webhook_hmac_secret" is empty
    When I send a GET to "/api/v1/unsubscribe?email=user@example.com&client=bdd-client&sig=anything"
    Then the response status should be 403

  Scenario: The confirmation form can be submitted as a browser would
    Given I am authenticated
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "form-user@example.com"}
      """
    Then the response status should be 201
    And I store the response "id" as "contact_id"
    Given I am not authenticated
    And a valid unsubscribe signature for "form-user@example.com" of client "bdd-client"
    When I send a GET to "/api/v1/unsubscribe?email=form-user@example.com&client=bdd-client&sig={unsub_sig}"
    Then the response status should be 200
    When I submit the confirmation form
    Then the response status should be 200
    And the response should contain "Successfully unsubscribed"
    Given I am authenticated
    When I send a GET to "/api/v1/contacts/{contact_id}"
    Then the response JSON "status" should be "unsubscribed"

  # ── Isolation between clients ─────────────────────────────────────────────

  Scenario: A link only unsubscribes the contact of the client that sent it
    Given I am authenticated as client "app-one" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "shared@example.com"}
      """
    Then I store the response "id" as "contact_one"
    Given I am authenticated as client "app-two" with scopes "mailler:read mailler:write"
    When I send a POST to "/api/v1/contacts" with
      """
      {"email": "shared@example.com"}
      """
    Then I store the response "id" as "contact_two"
    Given I am not authenticated
    And a valid unsubscribe signature for "shared@example.com" of client "app-one"
    When I send a POST to "/api/v1/unsubscribe?email=shared@example.com&client=app-one&sig={unsub_sig}"
    Then the response status should be 200
    Given I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/contacts/{contact_one}"
    Then the response JSON "status" should be "unsubscribed"
    Given I am authenticated as client "app-two" with scopes "mailler:read"
    When I send a GET to "/api/v1/contacts/{contact_two}"
    Then the response JSON "status" should be "active"

  Scenario: A signature issued for one client is rejected for another
    Given I am not authenticated
    And a valid unsubscribe signature for "shared@example.com" of client "app-one"
    When I send a POST to "/api/v1/unsubscribe?email=shared@example.com&client=app-two&sig={unsub_sig}"
    Then the response status should be 403

  Scenario: The client is required in the link
    Given I am not authenticated
    When I send a GET to "/api/v1/unsubscribe?email=user@example.com&sig=anything"
    Then the response status should be 422
