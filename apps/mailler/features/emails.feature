Feature: Email listing and details
  Stored emails can be browsed page by page, filtered by provider and status,
  and read one by one.

  Background:
    Given I am authenticated

  Scenario: Listing when no email exists
    When I send a GET to "/api/v1/emails"
    Then the response status should be 200
    And the response JSON "total" should be "0"
    And the response JSON "pages" should be "1"
    And the response JSON "items" should have 0 entries

  Scenario: Listing returns the stored emails
    Given the following emails are stored
      | to_email        | provider | status |
      | a@example.com   | brevo    | sent   |
      | b@example.com   | ses      | failed |
    When I send a GET to "/api/v1/emails"
    Then the response status should be 200
    And the response JSON "total" should be "2"
    And the response JSON "items" should include an entry with "to_email" equal to "a@example.com"
    And the response JSON "items" should include an entry with "to_email" equal to "b@example.com"

  Scenario: Listing is paginated
    Given the following emails are stored
      | to_email        |
      | a@example.com   |
      | b@example.com   |
      | c@example.com   |
    When I send a GET to "/api/v1/emails?page=2&page_size=2"
    Then the response status should be 200
    And the response JSON "total" should be "3"
    And the response JSON "pages" should be "2"
    And the response JSON "page" should be "2"
    And the response JSON "items" should have 1 entries

  Scenario: Listing can be filtered by provider
    Given the following emails are stored
      | to_email        | provider |
      | a@example.com   | brevo    |
      | b@example.com   | ses      |
    When I send a GET to "/api/v1/emails?provider=ses"
    Then the response status should be 200
    And the response JSON "total" should be "1"
    And the response JSON "items" should include an entry with "to_email" equal to "b@example.com"

  Scenario: Listing can be filtered by status
    Given the following emails are stored
      | to_email        | status  |
      | a@example.com   | sent    |
      | b@example.com   | pending |
    When I send a GET to "/api/v1/emails?status=sent"
    Then the response status should be 200
    And the response JSON "total" should be "1"
    And the response JSON "items" should not include an entry with "to_email" equal to "b@example.com"

  Scenario: Invalid pagination parameters are rejected
    When I send a GET to "/api/v1/emails?page=0"
    Then the response status should be 422

  Scenario: Reading an email by identifier
    Given the following emails are stored
      | alias    | to_email        | subject     | provider |
      | email_id | d@example.com   | Retrieve me | brevo    |
    When I send a GET to "/api/v1/emails/{email_id}"
    Then the response status should be 200
    And the response JSON "to_email" should be "d@example.com"
    And the response JSON "subject" should be "Retrieve me"
    And the response JSON "provider" should be "brevo"
    And the response JSON "status" should be "pending"

  Scenario: An email sent through the API can be read back
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "detail@example.com", "subject": "Round trip", "html_content": "<p>Hi</p>", "provider": "brevo"}
      """
    Then the response status should be 200
    And I store the response "id" as "email_id"
    When I send a GET to "/api/v1/emails/{email_id}"
    Then the response status should be 200
    And the response JSON "subject" should be "Round trip"

  Scenario: Reading an unknown email returns 404
    When I send a GET to "/api/v1/emails/00000000-0000-0000-0000-000000000000"
    Then the response status should be 404

  Scenario: Listing requires authentication
    Given I am not authenticated
    When I send a GET to "/api/v1/emails"
    Then the response status should be 401

  Scenario: Listing requires the read scope
    Given I am authenticated with scopes "mailler:send"
    When I send a GET to "/api/v1/emails"
    Then the response status should be 403

  Scenario: A client only lists its own emails
    Given the following emails are stored
      | to_email      | client_id |
      | a@example.com | app-one   |
      | b@example.com | app-two   |
    And I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/emails"
    Then the response status should be 200
    And the response JSON "total" should be "1"
    And the response JSON "items" should include an entry with "to_email" equal to "a@example.com"
    And the response JSON "items" should not include an entry with "to_email" equal to "b@example.com"

  Scenario: A client cannot read the email of another client
    Given the following emails are stored
      | alias   | to_email      | client_id |
      | foreign | b@example.com | app-two   |
    And I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/emails/{foreign}"
    Then the response status should be 404

  Scenario: A client reads its own email
    Given the following emails are stored
      | alias | to_email      | client_id |
      | own   | a@example.com | app-one   |
    And I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/emails/{own}"
    Then the response status should be 200
    And the response JSON "client_id" should be "app-one"

  Scenario: A client cannot ask for the emails of another client
    Given I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/emails?client_id=app-two"
    Then the response status should be 403

  Scenario: Emails without an owner are only visible to administrators
    Given the following emails are stored
      | to_email           |
      | orphan@example.com |
    And I am authenticated as client "app-one" with scopes "mailler:read"
    When I send a GET to "/api/v1/emails"
    Then the response JSON "total" should be "0"

  Scenario: An administrator lists every client and can narrow to one
    Given the following emails are stored
      | to_email      | client_id |
      | a@example.com | app-one   |
      | b@example.com | app-two   |
    And I am authenticated as client "ops" with scopes "mailler:read mailler:admin"
    When I send a GET to "/api/v1/emails"
    Then the response JSON "total" should be "2"
    When I send a GET to "/api/v1/emails?client_id=app-two"
    Then the response JSON "total" should be "1"
    And the response JSON "items" should include an entry with "to_email" equal to "b@example.com"

  Scenario: An email sent by a client is only readable by that client
    Given I am authenticated as client "app-one" with scopes "mailler:send mailler:read"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "detail@example.com", "subject": "Mine", "html_content": "<p>Hi</p>", "provider": "brevo"}
      """
    Then the response status should be 200
    And I store the response "id" as "mine"
    Given I am authenticated as client "app-two" with scopes "mailler:read"
    When I send a GET to "/api/v1/emails/{mine}"
    Then the response status should be 404
