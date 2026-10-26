Feature: Workflows
  A workflow is a named definition of the steps a team follows, with a status
  that goes from draft to active. Workflows are managed under
  /platform/{team_id}/workflows.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"

  Scenario: Creating a workflow
    When I send a POST request to "/platform/${team_id}/workflows" with the JSON '{"name": "Deploy Pipeline", "description": "Build, test, ship", "steps": {"build": "make", "ship": "deploy"}, "config": {"retries": 2}}'
    Then the response status is 201
    And the response JSON field "name" is "Deploy Pipeline"
    And the response JSON field "status" is "draft"
    And the response JSON field "steps.ship" is "deploy"
    And the response JSON field "config.retries" is "2"

  Scenario: Creating a workflow in an unknown team
    When I send a POST request to "/platform/6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11/workflows" with the JSON '{"name": "Deploy Pipeline"}'
    Then the response status is 404
    And the response detail is "Team not found"

  Scenario: Listing the workflows of a team
    Given I send a POST request to "/platform/${team_id}/workflows" with the JSON '{"name": "A"}'
    And I send a POST request to "/platform/${team_id}/workflows" with the JSON '{"name": "B"}'
    And I send a POST request to "/platform/team" with the JSON '{"name": "Other", "slug": "other"}'
    And I remember the response field "id" as "other_team_id"
    And I send a POST request to "/platform/${other_team_id}/workflows" with the JSON '{"name": "C"}'
    When I request "/platform/${team_id}/workflows"
    Then the response status is 200
    And the response JSON list has 2 items

  Scenario: Activating a workflow
    Given I send a POST request to "/platform/${team_id}/workflows" with the JSON '{"name": "Deploy Pipeline"}'
    And I remember the response field "id" as "workflow_id"
    When I send a PATCH request to "/platform/${team_id}/workflows/${workflow_id}" with the JSON '{"status": "active"}'
    Then the response status is 200
    And the response JSON field "status" is "active"
    And the response JSON field "name" is "Deploy Pipeline"

  Scenario: A workflow cannot be changed through another team
    Given I send a POST request to "/platform/${team_id}/workflows" with the JSON '{"name": "Deploy Pipeline"}'
    And I remember the response field "id" as "workflow_id"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Other", "slug": "other"}'
    And I remember the response field "id" as "other_team_id"
    When I send a PATCH request to "/platform/${other_team_id}/workflows/${workflow_id}" with the JSON '{"status": "active"}'
    Then the response status is 404
    And the response detail is "Workflow not found"

  Scenario: Deleting a workflow
    Given I send a POST request to "/platform/${team_id}/workflows" with the JSON '{"name": "Deploy Pipeline"}'
    And I remember the response field "id" as "workflow_id"
    When I send a DELETE request to "/platform/${team_id}/workflows/${workflow_id}"
    Then the response status is 204
    When I request "/platform/${team_id}/workflows"
    Then the response JSON list has 0 items

  Scenario: Creating a workflow needs the write scope
    Given I am authenticated with the scopes "team:platform:read"
    When I send a POST request to "/platform/${team_id}/workflows" with the JSON '{"name": "Deploy Pipeline"}'
    Then the response status is 403
