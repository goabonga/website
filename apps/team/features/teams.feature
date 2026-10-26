Feature: Team management
  A team groups the agents, workflows, tasks and memory of one organisation.
  Teams are managed under /platform/team with the platform scopes.

  Scenario: Creating a team
    Given I am authenticated with the scopes "team:platform:write"
    When I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering", "description": "Builds the product"}'
    Then the response status is 201
    And the response JSON field "name" is "Engineering"
    And the response JSON field "slug" is "engineering"
    And the response JSON field "is_active" is "True"

  Scenario: Reading a team
    Given I am authenticated with the scopes "team:platform:write team:platform:read"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Ops", "slug": "ops"}'
    And I remember the response field "id" as "team_id"
    When I request "/platform/team/${team_id}"
    Then the response status is 200
    And the response JSON field "slug" is "ops"

  Scenario: Listing teams
    Given I am authenticated with the scopes "team:platform:write team:platform:read"
    And I send a POST request to "/platform/team" with the JSON '{"name": "A", "slug": "a"}'
    And I send a POST request to "/platform/team" with the JSON '{"name": "B", "slug": "b"}'
    When I request "/platform/team"
    Then the response status is 200
    And the response JSON list has 2 items

  Scenario: Listing teams page by page
    Given I am authenticated with the scopes "team:platform:write team:platform:read"
    And I send a POST request to "/platform/team" with the JSON '{"name": "A", "slug": "a"}'
    And I send a POST request to "/platform/team" with the JSON '{"name": "B", "slug": "b"}'
    When I request "/platform/team?limit=1&offset=1"
    Then the response status is 200
    And the response JSON list has 1 items

  Scenario: Updating a team
    Given I am authenticated with the scopes "team:platform:write team:platform:read"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Ops", "slug": "ops"}'
    And I remember the response field "id" as "team_id"
    When I send a PATCH request to "/platform/team/${team_id}" with the JSON '{"description": "Runs the platform", "is_active": false}'
    Then the response status is 200
    And the response JSON field "description" is "Runs the platform"
    And the response JSON field "is_active" is "False"
    And the response JSON field "slug" is "ops"

  Scenario: Deleting a team
    Given I am authenticated with the scopes "team:platform:write team:platform:read"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Ops", "slug": "ops"}'
    And I remember the response field "id" as "team_id"
    When I send a DELETE request to "/platform/team/${team_id}"
    Then the response status is 204
    When I request "/platform/team/${team_id}"
    Then the response status is 404
    And the response detail is "Team not found"

  Scenario: Reading an unknown team
    Given I am authenticated with the scopes "team:platform:read"
    When I request "/platform/team/6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11"
    Then the response status is 404

  Scenario: Creating a team needs the write scope
    Given I am authenticated with the scopes "team:platform:read"
    When I send a POST request to "/platform/team" with the JSON '{"name": "Ops", "slug": "ops"}'
    Then the response status is 403

  Scenario: Listing teams needs authentication
    Given I am not authenticated
    When I request "/platform/team"
    Then the response status is 401
