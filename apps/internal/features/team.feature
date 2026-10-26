Feature: Team AI admin dashboard and agent management
  As an admin user with team permissions
  I want to manage teams, agents, workflows, conversations, and memory
  So that I can administrate the Team AI orchestration platform

  Background:
    Given I am a super admin

  # ==========================================================================
  # Dashboard
  # ==========================================================================

  @team
  Scenario: View team dashboard
    Given the team list returns data
    When I send a GET request to "/team"
    Then the response status code should be 200
    And the response should be HTML

  @team
  Scenario: View team dashboard unauthenticated
    Given I am not authenticated
    When I send a GET request to "/team"
    Then the response status code should be 302

  # ==========================================================================
  # Teams - CRUD
  # ==========================================================================

  @team
  Scenario: View new team form
    When I send a GET request to "/team/new"
    Then the response status code should be 200
    And the response should be HTML

  @team
  Scenario: Create a new team successfully
    Given creating a team succeeds
    When I send a POST request to "/team/new" with form data
      | field       | value           |
      | name        | My Team         |
      | slug        | my-team         |
      | description | A test team     |
      | config_json | {}              |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/team/"
    And I should be redirected to a URL containing "success="

  @team
  Scenario: Create a new team failure
    Given creating a team fails
    When I send a POST request to "/team/new" with form data
      | field | value    |
      | name  | Bad Team |
      | slug  | bad-team |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+create"

  @team
  Scenario: Create a team with invalid JSON config
    When I send a POST request to "/team/new" with form data
      | field       | value    |
      | name        | My Team  |
      | slug        | my-team  |
      | config_json | {invalid |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Invalid+JSON"

  @team
  Scenario: View team detail
    Given a team exists with id "team-1"
    When I send a GET request to "/team/team-1"
    Then the response status code should be 200
    And the response should be HTML

  @team
  Scenario: View team detail not found
    Given a team does not exist
    When I send a GET request to "/team/nonexistent"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/team"
    And I should be redirected to a URL containing "error="

  @team
  Scenario: View team edit form
    Given a team exists with id "team-1"
    When I send a GET request to "/team/team-1/edit"
    Then the response status code should be 200
    And the response should be HTML

  @team
  Scenario: View team edit form not found
    Given a team does not exist
    When I send a GET request to "/team/nonexistent/edit"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @team
  Scenario: Update a team successfully
    Given updating a team succeeds
    When I send a POST request to "/team/team-1/edit" with form data
      | field       | value         |
      | name        | Updated Team  |
      | description | Updated desc  |
      | config_json | {}            |
      | is_active   | true          |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/team/team-1"
    And I should be redirected to a URL containing "success="

  @team
  Scenario: Update a team failure
    Given updating a team fails
    When I send a POST request to "/team/team-1/edit" with form data
      | field | value        |
      | name  | Updated Team |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+update"

  @team
  Scenario: Delete a team successfully
    Given deleting a team succeeds
    When I send a POST request to "/team/team-1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/team"
    And I should be redirected to a URL containing "success="

  @team
  Scenario: Delete a team failure
    Given deleting a team fails
    When I send a POST request to "/team/team-1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+delete"

  # ==========================================================================
  # Agents
  # ==========================================================================

  @team-agents
  Scenario: List agents for a team
    Given a team exists with id "team-1"
    And the team agents list returns data for team "team-1"
    When I send a GET request to "/team/team-1/agents"
    Then the response status code should be 200
    And the response should be HTML

  @team-agents
  Scenario: List agents when team not found
    Given a team does not exist
    When I send a GET request to "/team/nonexistent/agents"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @team-agents
  Scenario: View new agent form
    Given a team exists with id "team-1"
    When I send a GET request to "/team/team-1/agents/new"
    Then the response status code should be 200
    And the response should be HTML

  @team-agents
  Scenario: View new agent form when team not found
    Given a team does not exist
    When I send a GET request to "/team/nonexistent/agents/new"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @team-agents
  Scenario: Create an agent successfully
    Given creating a team agent succeeds for team "team-1"
    When I send a POST request to "/team/team-1/agents/new" with form data
      | field         | value          |
      | name          | My Agent       |
      | role          | assistant      |
      | description   | A test agent   |
      | system_prompt | You are helpful|
      | model         | gpt-4o         |
      | provider      | openai         |
      | config_json   | {}             |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/team/team-1/agents/"
    And I should be redirected to a URL containing "success="

  @team-agents
  Scenario: Create an agent failure
    Given creating a team agent fails for team "team-1"
    When I send a POST request to "/team/team-1/agents/new" with form data
      | field | value     |
      | name  | Bad Agent |
      | role  | assistant |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+create+agent"

  @team-agents
  Scenario: View agent detail
    Given a team exists with id "team-1"
    And a team agent exists with id "agent-1" for team "team-1"
    When I send a GET request to "/team/team-1/agents/agent-1"
    Then the response status code should be 200
    And the response should be HTML

  @team-agents
  Scenario: View agent detail when agent not found
    Given a team exists with id "team-1"
    And a team agent does not exist for team "team-1"
    When I send a GET request to "/team/team-1/agents/nonexistent"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Agent+not+found"

  @team-agents
  Scenario: View agent edit form
    Given a team exists with id "team-1"
    And a team agent exists with id "agent-1" for team "team-1"
    When I send a GET request to "/team/team-1/agents/agent-1/edit"
    Then the response status code should be 200
    And the response should be HTML

  @team-agents
  Scenario: Update an agent successfully
    Given updating a team agent succeeds for team "team-1"
    When I send a POST request to "/team/team-1/agents/agent-1/edit" with form data
      | field       | value           |
      | name        | Updated Agent   |
      | role        | assistant       |
      | model       | gpt-4o          |
      | provider    | openai          |
      | config_json | {}              |
      | is_active   | true            |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/team/team-1/agents/agent-1"
    And I should be redirected to a URL containing "success="

  @team-agents
  Scenario: Update an agent failure
    Given updating a team agent fails for team "team-1"
    When I send a POST request to "/team/team-1/agents/agent-1/edit" with form data
      | field | value         |
      | name  | Updated Agent |
      | role  | assistant     |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+update+agent"

  @team-agents
  Scenario: Delete an agent successfully
    Given deleting a team agent succeeds for team "team-1"
    When I send a POST request to "/team/team-1/agents/agent-1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/team/team-1/agents"
    And I should be redirected to a URL containing "success="

  @team-agents
  Scenario: Delete an agent failure
    Given deleting a team agent fails for team "team-1"
    When I send a POST request to "/team/team-1/agents/agent-1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+delete+agent"

  # ==========================================================================
  # Workflows
  # ==========================================================================

  @team-workflows
  Scenario: List workflows for a team
    Given a team exists with id "team-1"
    And the team workflows list returns data for team "team-1"
    When I send a GET request to "/team/team-1/workflows"
    Then the response status code should be 200
    And the response should be HTML

  @team-workflows
  Scenario: List workflows when team not found
    Given a team does not exist
    When I send a GET request to "/team/nonexistent/workflows"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @team-workflows
  Scenario: View new workflow form
    Given a team exists with id "team-1"
    When I send a GET request to "/team/team-1/workflows/new"
    Then the response status code should be 200
    And the response should be HTML

  @team-workflows
  Scenario: Create a workflow successfully
    Given creating a team workflow succeeds for team "team-1"
    When I send a POST request to "/team/team-1/workflows/new" with form data
      | field       | value            |
      | name        | My Workflow      |
      | description | A test workflow  |
      | steps_json  | {}               |
      | config_json | {}               |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/team/team-1/workflows"
    And I should be redirected to a URL containing "success="

  @team-workflows
  Scenario: Create a workflow failure
    Given creating a team workflow fails for team "team-1"
    When I send a POST request to "/team/team-1/workflows/new" with form data
      | field | value        |
      | name  | Bad Workflow |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+create+workflow"

  @team-workflows
  Scenario: Create a workflow with invalid JSON
    Given a team exists with id "team-1"
    When I send a POST request to "/team/team-1/workflows/new" with form data
      | field      | value    |
      | name       | Workflow |
      | steps_json | {broken  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Invalid+JSON"

  @team-workflows
  Scenario: View workflow edit form
    Given a team exists with id "team-1"
    And a team workflow exists with id "wf-1" for team "team-1"
    When I send a GET request to "/team/team-1/workflows/wf-1/edit"
    Then the response status code should be 200
    And the response should be HTML

  @team-workflows
  Scenario: View workflow edit form not found
    Given a team exists with id "team-1"
    And a team workflow does not exist for team "team-1"
    When I send a GET request to "/team/team-1/workflows/nonexistent/edit"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Workflow+not+found"

  @team-workflows
  Scenario: Update a workflow successfully
    Given a team exists with id "team-1"
    And updating a team workflow succeeds for team "team-1"
    When I send a POST request to "/team/team-1/workflows/wf-1/edit" with form data
      | field           | value             |
      | name            | Updated Workflow  |
      | description     | Updated desc      |
      | steps_json      | {}                |
      | workflow_status | active            |
      | config_json     | {}                |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/team/team-1/workflows"
    And I should be redirected to a URL containing "success="

  @team-workflows
  Scenario: Update a workflow failure
    Given a team exists with id "team-1"
    And updating a team workflow fails for team "team-1"
    When I send a POST request to "/team/team-1/workflows/wf-1/edit" with form data
      | field | value            |
      | name  | Updated Workflow |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+update+workflow"

  @team-workflows
  Scenario: Delete a workflow successfully
    Given deleting a team workflow succeeds for team "team-1"
    When I send a POST request to "/team/team-1/workflows/wf-1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/team/team-1/workflows"
    And I should be redirected to a URL containing "success="

  @team-workflows
  Scenario: Delete a workflow failure
    Given deleting a team workflow fails for team "team-1"
    When I send a POST request to "/team/team-1/workflows/wf-1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+delete+workflow"

  # ==========================================================================
  # Conversations
  # ==========================================================================

  @team-conversations
  Scenario: List conversations for a team
    Given a team exists with id "team-1"
    And the team conversations list returns data
    When I send a GET request to "/team/team-1/conversations"
    Then the response status code should be 200
    And the response should be HTML

  @team-conversations
  Scenario: List conversations when team not found
    Given a team does not exist
    When I send a GET request to "/team/nonexistent/conversations"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  @team-conversations
  Scenario: View conversation detail
    Given a team exists with id "team-1"
    And a team conversation exists with id "conv-1"
    When I send a GET request to "/team/team-1/conversations/conv-1"
    Then the response status code should be 200
    And the response should be HTML

  @team-conversations
  Scenario: View conversation detail not found
    Given a team exists with id "team-1"
    And a team conversation does not exist
    When I send a GET request to "/team/team-1/conversations/nonexistent"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Conversation+not+found"

  @team-conversations
  Scenario: Delete a conversation successfully
    Given deleting a team conversation succeeds
    When I send a POST request to "/team/team-1/conversations/conv-1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "/team/team-1/conversations"
    And I should be redirected to a URL containing "success="

  @team-conversations
  Scenario: Delete a conversation failure
    Given deleting a team conversation fails
    When I send a POST request to "/team/team-1/conversations/conv-1/delete"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Failed+to+delete+conversation"

  # ==========================================================================
  # Memory
  # ==========================================================================

  @team-memory
  Scenario: List memory entries for a team
    Given a team exists with id "team-1"
    And the team memory list returns data for team "team-1"
    When I send a GET request to "/team/team-1/memory"
    Then the response status code should be 200
    And the response should be HTML

  @team-memory
  Scenario: List memory when team not found
    Given a team does not exist
    When I send a GET request to "/team/nonexistent/memory"
    Then the response status code should be 303
    And I should be redirected to a URL containing "error="

  # --- Sidebar ---

  Scenario: Sidebar on the team dashboard
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And the team list returns data
    When I send a GET request to "/team"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the new team form
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    When I send a GET request to "/team/new"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the team detail
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    When I send a GET request to "/team/team-1"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the team edit form
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    When I send a GET request to "/team/team-1/edit"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the agents list
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    And the team agents list returns data for team "team-1"
    When I send a GET request to "/team/team-1/agents"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the new agent form
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    When I send a GET request to "/team/team-1/agents/new"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the agent detail
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    And a team agent exists with id "agent-1" for team "team-1"
    When I send a GET request to "/team/team-1/agents/agent-1"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the agent edit form
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    And a team agent exists with id "agent-1" for team "team-1"
    When I send a GET request to "/team/team-1/agents/agent-1/edit"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the skill edit form
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    And a team agent exists with id "agent-1" for team "team-1"
    And a team agent skill exists with id "skill-1"
    When I send a GET request to "/team/team-1/agents/agent-1/skills/skill-1/edit"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the workflows list
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    And the team workflows list returns data for team "team-1"
    When I send a GET request to "/team/team-1/workflows"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the new workflow form
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    When I send a GET request to "/team/team-1/workflows/new"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the workflow edit form
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    And a team workflow exists with id "wf-1" for team "team-1"
    When I send a GET request to "/team/team-1/workflows/wf-1/edit"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the run agent form
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    And the team agents list returns data for team "team-1"
    When I send a GET request to "/team/team-1/run"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the conversations list
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    And the team conversations list returns data
    When I send a GET request to "/team/team-1/conversations"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the conversation detail
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    And a team conversation exists with id "conv-1"
    When I send a GET request to "/team/team-1/conversations/conv-1"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the memory list
    Given I am authenticated with only the scopes "team:* vpn:admin billing:read" granted by token exchange
    And a team exists with id "team-1"
    And the team memory list returns data for team "team-1"
    When I send a GET request to "/team/team-1/memory"
    Then the response status code should be 200
    And the active sidebar link should be "/team"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario Outline: Sidebar gated links follow the scopes on the team dashboard
    Given I am authenticated with only the scopes "<scopes>" granted by token exchange
    And the team list returns data
    When I send a GET request to "/team"
    Then the response status code should be 200
    And the sidebar link to "/vpn/sessions" should be <vpn>
    And the sidebar link to "/billing" should be <billing>

    Examples:
      | scopes                        | vpn     | billing |
      | team:*                        | hidden  | hidden  |
      | team:* vpn:admin              | visible | hidden  |
      | team:* billing:read           | hidden  | visible |
      | team:* vpn:admin billing:read | visible | visible |
      | *                             | visible | visible |
