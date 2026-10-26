Feature: GitHub webhook proxy
  As the webhooks service
  I want to receive GitHub webhook events
  So that I can forward them to the internal API

  Scenario: Forward a push event
    When I send a POST request to "/webhooks/github" with body
      """
      {"action": "push", "ref": "refs/heads/main", "repository": {"full_name": "org/repo"}}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward a pull request event
    When I send a POST request to "/webhooks/github" with body
      """
      {"action": "opened", "pull_request": {"number": 42, "title": "Fix bug"}}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward a release event
    When I send a POST request to "/webhooks/github" with body
      """
      {"action": "published", "release": {"tag_name": "v1.0.0"}}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Empty body returns 200
    When I send an empty POST request to "/webhooks/github"
    Then the response status code should be 200
    And the internal API should not have been called

  Scenario: Reject invalid signature when secret is configured
    Given the GitHub webhook secret is "gh-secret"
    And the request has header "X-Hub-Signature-256" with value "sha256=invalid"
    When I send a POST request to "/webhooks/github" with headers and body
      """
      {"action": "push", "ref": "refs/heads/main"}
      """
    Then the response status code should be 401
    And the internal API should not have been called

  Scenario: Accept valid signature when secret is configured
    Given the GitHub webhook secret is "gh-secret"
    When I send a GitHub-signed POST request to "/webhooks/github" with body
      """
      {"action": "push", "ref": "refs/heads/main"}
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward Authorization header when token is configured
    Given the GitHub internal API token is "github-secret-token"
    When I send a POST request to "/webhooks/github" with body
      """
      {"action": "push", "ref": "refs/heads/main"}
      """
    Then the response status code should be 200
    And the internal API should have been called
    And the internal API should have received authorization "Bearer github-secret-token"

  Scenario: No Authorization header when token is not configured
    When I send a POST request to "/webhooks/github" with body
      """
      {"action": "push", "ref": "refs/heads/main"}
      """
    Then the response status code should be 200
    And the internal API should have been called
    And the internal API should not have received authorization

  Scenario: Reject a request without signature when secret is configured
    Given the GitHub webhook secret is "gh-secret"
    When I send a POST request to "/webhooks/github" with body
      """
      {"action": "push", "ref": "refs/heads/main"}
      """
    Then the response status code should be 401
    And the internal API should not have been called

  Scenario: Forward the GitHub headers to the internal API
    Given the request has header "X-GitHub-Event" with value "push"
    And the request has header "X-GitHub-Delivery" with value "delivery-1"
    When I send a POST request to "/webhooks/github" with headers and body
      """
      {"action": "push", "ref": "refs/heads/main"}
      """
    Then the response status code should be 200
    And the internal API should have received header "X-GitHub-Event" with value "push"
    And the internal API should have received header "X-GitHub-Delivery" with value "delivery-1"

  Scenario: Forward the raw body to the GitHub internal endpoint
    When I send a POST request to "/webhooks/github" with body
      """
      {"action": "push", "ref": "refs/heads/main"}
      """
    Then the internal API should have received path "/webhooks/github"
    And the internal API should have received the request body

  Scenario: Bad gateway when the internal API cannot be reached
    Given the internal API cannot be reached
    When I send a POST request to "/webhooks/github" with body
      """
      {"action": "push", "ref": "refs/heads/main"}
      """
    Then the response status code should be 502

  Scenario: Service unavailable when the internal API is not configured
    Given the GitHub internal API is not configured
    When I send a POST request to "/webhooks/github" with body
      """
      {"action": "push", "ref": "refs/heads/main"}
      """
    Then the response status code should be 503
    And the internal API should not have been called
