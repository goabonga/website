Feature: Client sending limits
  A client can be given a rate limit (emails per minute) and a daily quota
  (emails per UTC day). A request that would exceed one of them is refused
  with 429 and a Retry-After header; administrators are never limited.

  Scenario: The rate limit refuses the emails beyond the limit
    Given the following clients are registered
      | client_id | rate_limit_per_minute |
      | app-one   | 2                     |
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "one@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 200
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "two@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 200
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "three@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 429
    And the response should contain "Rate limit exceeded"
    And the response header "retry-after" should be "60"
    And the email to "three@example.com" should no longer be stored

  Scenario: The limits of a client do not affect the others
    Given the following clients are registered
      | client_id | rate_limit_per_minute |
      | app-one   | 1                     |
      | app-two   |                       |
    And the following emails are stored for client "app-one"
      | to_email      |
      | a@example.com |
    And I am authenticated as client "app-two" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "b@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 200

  Scenario: Emails older than a minute do not count against the rate limit
    Given the following clients are registered
      | client_id | rate_limit_per_minute |
      | app-one   | 1                     |
    And the following emails are stored for client "app-one"
      | to_email      | age |
      | old@example.com | 5m  |
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "new@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 200

  Scenario: The daily quota refuses the emails beyond the quota
    Given the following clients are registered
      | client_id | daily_quota |
      | app-one   | 2           |
    And the following emails are stored for client "app-one"
      | to_email      |
      | a@example.com |
      | b@example.com |
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "c@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 429
    And the response should contain "Daily quota exceeded"
    When I send a POST to "/api/v1/schedule" with
      """
      {"to_email": "d@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "scheduled_at": "2030-01-01T10:00:00Z"}
      """
    Then the response status should be 429

  Scenario: Emails of earlier days do not count against the quota
    Given the following clients are registered
      | client_id | daily_quota |
      | app-one   | 1           |
    And the following emails are stored for client "app-one"
      | to_email        | age |
      | old@example.com | 2d  |
    And I am authenticated as client "app-one" with scopes "mailler:send"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "new@example.com", "subject": "Hi", "html_content": "<p>Hi</p>"}
      """
    Then the response status should be 200

  Scenario: A campaign counts against the daily quota as a whole
    Given the following clients are registered
      | client_id | daily_quota |
      | app-one   | 1           |
    And I am authenticated as client "app-one" with scopes "mailler:read mailler:write mailler:send"
    When I send a POST to "/api/v1/templates" with
      """
      {"slug": "tpl", "name": "Template", "subject_template": "Hello", "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"}
      """
    Then I store the response "id" as "template_id"
    When I send a POST to "/api/v1/contact-groups" with
      """
      {"slug": "grp", "name": "Group"}
      """
    Then I store the response "id" as "group_id"
    When I send a POST to "/api/v1/contacts/bulk" with
      """
      {"contacts": [{"email": "ann@example.com"}, {"email": "bob@example.com"}]}
      """
    Then the response status should be 201
    When I send a GET to "/api/v1/contacts"
    Then I add all listed contacts to the group "group_id"
    When I send a POST to "/api/v1/campaigns" with
      """
      {"name": "Big", "template_id": {template_id}, "group_id": {group_id}}
      """
    Then I store the response "id" as "campaign_id"
    When I send a POST to "/api/v1/campaigns/{campaign_id}/send"
    Then the response status should be 429
    And the response should contain "Daily quota exceeded"
    When I send a GET to "/api/v1/campaigns/{campaign_id}"
    Then the response JSON "status" should be "draft"

  Scenario: Administrators are never limited
    Given the following clients are registered
      | client_id | rate_limit_per_minute | daily_quota |
      | ops       | 1                     | 1           |
    And I am authenticated as client "ops" with scopes "mailler:send mailler:admin"
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "one@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "from_email": "ops@platform.example", "provider": "brevo"}
      """
    Then the response status should be 200
    When I send a POST to "/api/v1/send" with
      """
      {"to_email": "two@example.com", "subject": "Hi", "html_content": "<p>Hi</p>", "from_email": "ops@platform.example", "provider": "brevo"}
      """
    Then the response status should be 200

  Scenario: Limits are managed through the registry API
    Given I am authenticated as unregistered client "ops" with scopes "mailler:admin"
    When I send a POST to "/api/v1/clients" with
      """
      {"client_id": "app-one", "rate_limit_per_minute": 30, "daily_quota": 1000}
      """
    Then the response status should be 201
    And the response JSON "rate_limit_per_minute" should be "30"
    And the response JSON "daily_quota" should be "1000"
    When I send a PUT to "/api/v1/clients/app-one" with
      """
      {"daily_quota": 5}
      """
    Then the response status should be 200
    And the response JSON "daily_quota" should be "5"
    And the response JSON "rate_limit_per_minute" should be "30"
    When I send a PUT to "/api/v1/clients/app-one" with
      """
      {"rate_limit_per_minute": 0}
      """
    Then the response status should be 422
