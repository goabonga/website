Feature: Seed data
  A new installation starts with the GOABONGA startup team: a team, nineteen
  agents with a role, a model and a set of tools, and three or four skills per
  agent. The data is inserted by data migrations; the scenarios run them
  against a recording connection (PostgreSQL itself is not needed).

  Scenario: The seed creates the GOABONGA team
    When the seed migration "0008_seed_goabonga_team.py" is applied
    Then the seed inserted the team "goabonga" with the orchestration enabled every 15 minutes

  Scenario: The seed creates one agent per role
    When the seed migration "0008_seed_goabonga_team.py" is applied
    Then the seed inserted 19 agents with different roles
    And the seeded agents include the roles "ceo, cto, developer, qa, devops"
    And the seeded agents use the providers "openai, anthropic"

  Scenario: Every tool of the seeded agents exists
    When the seed migration "0008_seed_goabonga_team.py" is applied
    Then every tool of the seeded agents is registered

  Scenario: The tools added by later revisions follow the tool that justifies them
    Then every tool pair of "0010_add_github_crud_tools.py" is registered
    And every tool pair of "0011_add_memory_crud_tools.py" is registered

  Scenario: The seeded team can be orchestrated by its CEO
    Given I am authenticated with the scopes "team:platform:read"
    And the seed migration "0008_seed_goabonga_team.py" is applied
    And the seeded team and agents are loaded in the database
    And the task workers use the database of the scenario
    When the auto orchestration runs for the team "goabonga"
    Then the orchestration status is "created"

  Scenario: The seed adds skills to every agent
    When the seed migration "0012_seed_goabonga_skills.py" is applied for every role
    Then the seed inserted skills for all 19 roles with 3 or 4 skills each
    And every seeded skill is a valid agent skill

  Scenario: Skills are skipped for a missing team or agent
    When the seed migration "0012_seed_goabonga_skills.py" is applied without a team
    Then the seed inserted no skill

  Scenario: Downgrading removes what was seeded
    When the seed migration "0008_seed_goabonga_team.py" is reverted
    Then the seed deleted the agents and then the team
