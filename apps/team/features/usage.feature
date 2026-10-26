Feature: Usage reporting
  Services and agents report what they did: each event is stored in the
  execution log of the team. Events are posted under /usage/{team_id}.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write team:write"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I remember the response field "id" as "agent_id"

  Scenario: Reporting a usage event
    When I send a POST request to "/usage/${team_id}/report" with the JSON '{"agent_id": "${agent_id}", "action": "task.completed", "details": {"duration": 12}}'
    Then the response status is 201
    And the response JSON field "action" is "task.completed"
    And the response JSON field "details.duration" is "12"
    And the response JSON field "agent_id" is "${agent_id}"
    And 1 "task.completed" execution log entries exist

  Scenario: An event keeps the timestamp it was reported with
    When I send a POST request to "/usage/${team_id}/report" with the JSON '{"agent_id": "${agent_id}", "action": "task.started", "timestamp": "2026-03-01T10:00:00Z"}'
    Then the response status is 201
    And the response JSON field "timestamp" is "2026-03-01T10:00:00"

  Scenario: An event without timestamp is stamped with the current time
    When I send a POST request to "/usage/${team_id}/report" with the JSON '{"agent_id": "${agent_id}", "action": "task.started"}'
    Then the response status is 201
    And the response JSON field "timestamp" is not empty

  Scenario: Reporting several events at once
    When I send a POST request to "/usage/${team_id}/batch" with the JSON '{"events": [{"agent_id": "${agent_id}", "action": "tool.called"}, {"agent_id": "${agent_id}", "action": "tool.called"}, {"agent_id": "${agent_id}", "action": "task.completed"}]}'
    Then the response status is 201
    And the response JSON field "created" is "3"
    And 2 "tool.called" execution log entries exist

  Scenario: A batch needs at least one event
    When I send a POST request to "/usage/${team_id}/batch" with the JSON '{"events": []}'
    Then the response status is 422

  Scenario: An action is limited to 100 characters
    When I send a POST request to "/usage/${team_id}/report" with the JSON '{"agent_id": "${agent_id}", "action": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
    Then the response status is 422

  Scenario: Reporting usage for an unknown team
    When I send a POST request to "/usage/6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11/report" with the JSON '{"agent_id": "${agent_id}", "action": "task.completed"}'
    Then the response status is 404
    And the response detail is "Team not found"

  Scenario: Reporting usage needs the team:write scope
    Given I am authenticated with the scopes "team:platform:read team:platform:write"
    When I send a POST request to "/usage/${team_id}/report" with the JSON '{"agent_id": "${agent_id}", "action": "task.completed"}'
    Then the response status is 403
