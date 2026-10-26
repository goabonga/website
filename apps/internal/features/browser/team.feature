@browser
Feature: Team AI administration in a browser
  As an operator with the team permissions
  I want to manage teams, agents, workflows, conversations and memory
  So that I can run the AI agents of the platform

  Background:
    Given the team list returns data
    And a team exists with id "team-1"
    And the team agents list returns data for team "team-1"
    And a team agent exists with id "agent-1" for team "team-1"
    And the team workflows list returns data for team "team-1"
    And a team workflow exists with id "wf-1" for team "team-1"
    And the team conversations list returns data
    And a team conversation exists with id "conv-1"
    And the team memory list returns data for team "team-1"

  # --- Access and sidebar ---

  Scenario: The dashboard lists the teams
    Given I sign in with the scopes "team:*"
    When I navigate to "/team"
    Then the page title should be "Team AI Dashboard - Internal Admin"
    And I should see "Teams (1)"
    And I should see "Test Team"
    And the sidebar menu should highlight only "Team AI"
    And the browser should report no errors

  Scenario: The Team AI link leads to the dashboard
    Given I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/agents"
    Then the sidebar menu should highlight only "Team AI"
    When I follow the sidebar link "Team AI"
    Then the URL should be "/team"

  Scenario: A user without the team scope gets the access denied page
    Given I sign in with the scopes "contacts:read"
    When I navigate to "/team"
    Then the page title should contain "Access Denied"
    And I should see "team:read"

  Scenario: An anonymous visitor comes back to the page asked for after the login
    Given a user holding the scopes "team:*" exists at the provider
    When I navigate to "/team/team-1/agents"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/team/team-1/agents"
    And I should see "Test Agent"

  Scenario: A user who may only read does not see the buttons that change things
    Given I sign in with the scopes "team:read"
    When I navigate to "/team/team-1"
    Then I should see "Test Team"
    And "Delete Team" should be hidden

  # --- Teams ---

  Scenario: A team is created from the form
    Given creating a team succeeds
    And I sign in with the scopes "team:*"
    When I navigate to "/team"
    And I click "+ New Team"
    Then the URL should be "/team/new"
    When I fill "Name" with "Research"
    And I fill "Slug" with "research"
    And I fill "Description" with "The research team"
    And I click "Create Team"
    Then the URL should contain "/team/team-new?success="
    And I should see "Team created successfully"
    And the team service should have been asked to create the team "Research"

  Scenario: A team the service refuses is reported on the form
    Given creating a team fails
    And I sign in with the scopes "team:*"
    When I navigate to "/team/new"
    And I fill "Name" with "Research"
    And I fill "Slug" with "research"
    And I click "Create Team"
    Then the URL should contain "/team/new?error="
    And I should see "Failed to create team"

  Scenario: A configuration that is not JSON is refused
    Given creating a team succeeds
    And I sign in with the scopes "team:*"
    When I navigate to "/team/new"
    And I fill "Name" with "Research"
    And I fill "Slug" with "research"
    And I fill "Config (JSON)" with "{not json"
    And I click "Create Team"
    Then I should see "Invalid JSON in config"
    And the team service should not have been asked to create a team

  Scenario: The detail of a team links to its agents, workflows and conversations
    Given I sign in with the scopes "team:*"
    When I navigate to "/team"
    And I click "Test Team"
    Then the URL should be "/team/team-1"
    And I should see "Agents (1)"
    And I should see "Test Agent"
    And I should see "Workflows (1)"
    When I click "Launch Agent"
    Then the URL should be "/team/team-1/run"

  Scenario: A team that does not exist sends the user back to the dashboard
    Given a team does not exist
    And I sign in with the scopes "team:*"
    When I navigate to "/team/unknown"
    Then the URL should contain "/team?error="
    And I should see "Team not found"

  Scenario: A team is updated from its edit form
    Given updating a team succeeds
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1"
    And I click "Edit"
    Then the URL should be "/team/team-1/edit"
    When I fill "Name" with "Renamed team"
    And I click "Update Team"
    Then the URL should contain "/team/team-1?success="
    And I should see "Team updated successfully"

  Scenario: A team the service cannot update is reported on the form
    Given updating a team fails
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/edit"
    And I click "Update Team"
    Then I should see "Failed to update team"

  Scenario: A team is deleted after a confirmation
    Given deleting a team succeeds
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1"
    And I click "Delete Team"
    Then the page should have asked for a confirmation containing "delete this team"
    And the URL should contain "/team?success="
    And I should see "Team deleted successfully"

  Scenario: Dismissing the confirmation keeps the team
    Given deleting a team succeeds
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1"
    And I dismiss the next confirmation
    And I click "Delete Team"
    Then the URL should be "/team/team-1"
    And the team service should not have been asked to delete a team

  Scenario: A team the service cannot delete is reported
    Given deleting a team fails
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1"
    And I click "Delete Team"
    Then I should see "Failed to delete team"

  # --- Agents ---

  Scenario: The agents of a team are listed
    Given I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/agents"
    Then I should see "Agents - Test Team"
    And I should see "gpt-4o"
    When I click "Test Agent"
    Then the URL should be "/team/team-1/agents/agent-1"
    And I should see "You are helpful."

  Scenario: An agent is created from the form
    Given creating a team agent succeeds for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/agents"
    And I click "+ New Agent"
    Then the URL should be "/team/team-1/agents/new"
    When I fill "Name" with "Reviewer"
    And I fill "Role" with "reviewer"
    And I fill "System Prompt" with "Review the code."
    And I select "gpt-4o-mini" from "Model"
    And I click "Create Agent"
    Then the URL should contain "/team/team-1/agents/agent-new?success="
    And I should see "Agent created successfully"

  Scenario: Credentials are added to an agent with the form
    Given creating a team agent succeeds for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/agents/new"
    And I fill "Name" with "Reviewer"
    And I fill "Role" with "reviewer"
    And I click "+ Add Credential"
    And I fill "css=.credential-key" with "api_key"
    And I fill "css=.credential-value" with "secret"
    And I click "Create Agent"
    Then the URL should contain "/team/team-1/agents/agent-new?success="

  Scenario: An agent the service refuses is reported on the form
    Given creating a team agent fails for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/agents/new"
    And I fill "Name" with "Reviewer"
    And I fill "Role" with "reviewer"
    And I click "Create Agent"
    Then I should see "Failed to create agent"

  Scenario: An agent that does not exist sends the user back to the list
    Given a team agent does not exist for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/agents/unknown"
    Then the URL should contain "/team/team-1/agents?error="
    And I should see "Agent not found"

  Scenario: An agent is updated from its edit form
    Given updating a team agent succeeds for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/agents/agent-1"
    And I click "Edit"
    Then the URL should be "/team/team-1/agents/agent-1/edit"
    When I fill "Name" with "Senior reviewer"
    And I click "Update Agent"
    Then the URL should contain "/team/team-1/agents/agent-1?success="
    And I should see "Agent updated successfully"

  Scenario: An agent is deleted after a confirmation
    Given deleting a team agent succeeds for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/agents/agent-1"
    And I click "Delete Agent"
    Then the page should have asked for a confirmation containing "delete this agent"
    And the URL should contain "/team/team-1/agents?success="
    And I should see "Agent deleted successfully"

  Scenario: An agent the service cannot delete is reported
    Given deleting a team agent fails for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/agents/agent-1"
    And I click "Delete Agent"
    Then I should see "Failed to delete agent"

  Scenario: A skill whose name has an apostrophe can be deleted
    Given the agent "agent-1" has a skill called "O'Reilly search"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/agents/agent-1/edit"
    Then I should see "O'Reilly search"
    When I click "css=form[action$='/skills/skill-1/delete'] button"
    Then the page should have asked for a confirmation containing "Delete skill O'Reilly search?"
    And the browser should report no errors

  # --- Workflows ---

  Scenario: The workflows of a team are listed
    Given I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/workflows"
    Then I should see "Workflows - Test Team"
    And I should see "Test Workflow"

  Scenario: A workflow is created with a step
    Given creating a team workflow succeeds for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/workflows"
    And I click "+ New Workflow"
    Then the URL should be "/team/team-1/workflows/new"
    When I fill "Name" with "Review flow"
    And I click "+ Add First Step"
    And I click "Create Workflow"
    Then the URL should contain "/team/team-1/workflows?success="
    And I should see "Workflow created successfully"

  Scenario: A workflow the service refuses is reported on the form
    Given creating a team workflow fails for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/workflows/new"
    And I fill "Name" with "Review flow"
    And I click "Create Workflow"
    Then I should see "Failed to create workflow"

  Scenario: A workflow is updated from its edit form
    Given updating a team workflow succeeds for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/workflows"
    And I click "Edit"
    Then the URL should be "/team/team-1/workflows/wf-1/edit"
    When I fill "Name" with "Renamed flow"
    And I click "Update Workflow"
    Then the URL should contain "/team/team-1/workflows?success="
    And I should see "Workflow updated successfully"

  Scenario: A workflow is deleted after a confirmation
    Given deleting a team workflow succeeds for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/workflows"
    And I click "Delete"
    Then the page should have asked for a confirmation containing "Delete this workflow?"
    And I should see "Workflow deleted successfully"

  Scenario: A workflow the service cannot delete is reported
    Given deleting a team workflow fails for team "team-1"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/workflows"
    And I click "Delete"
    Then I should see "Failed to delete workflow"

  # --- Launching an agent ---

  Scenario: An agent task is launched from the team page
    Given launching an agent task succeeds
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/run"
    And I fill "Task Title" with "Review"
    And I fill "Message / Prompt" with "Please review the change"
    And I click "Launch Agent" in the page content
    Then the URL should contain "/team/team-1/conversations?success="
    And I should see "Agent task launched successfully"

  Scenario: A task the service refuses is reported on the form
    Given launching an agent task fails
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/run"
    And I fill "Task Title" with "Review"
    And I fill "Message / Prompt" with "Please review the change"
    And I click "Launch Agent" in the page content
    Then I should see "Failed to launch agent task"

  # --- Conversations ---

  Scenario: The conversations of a team are listed with their detail
    Given a team message says "Hello from the agent"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/conversations"
    Then I should see "Conversations - Test Team"
    And I should see "Test Conversation"
    When I click "Test Conversation"
    Then the URL should be "/team/team-1/conversations/conv-1"
    And I should see "Hello from the agent"
    And the sidebar menu should highlight only "Team AI"

  Scenario: A message with markup is shown as text
    Given a team message says "<img src=x onerror=alert(1)> done"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/conversations/conv-1"
    Then I should see "<img src=x onerror=alert(1)> done"
    And "css=.message-text img" should be hidden
    And the browser should report no errors

  Scenario: A conversation that does not exist sends the user back to the list
    Given a team conversation does not exist
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/conversations/unknown"
    Then the URL should contain "/team/team-1/conversations?error="
    And I should see "Conversation not found"

  Scenario: A conversation is deleted after a confirmation
    Given a team message says "Hello"
    And deleting a team conversation succeeds
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/conversations/conv-1"
    And I click "Delete Conversation"
    Then the page should have asked for a confirmation containing "Delete this conversation"
    And I should see "Conversation deleted successfully"

  Scenario: A conversation the service cannot delete is reported
    Given a team message says "Hello"
    And deleting a team conversation fails
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/conversations/conv-1"
    And I click "Delete Conversation"
    Then I should see "Failed to delete conversation"

  Scenario: A conversation is deleted from the list after a confirmation
    Given deleting a team conversation succeeds
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/conversations"
    And I click "Delete" in the page content
    Then the page should have asked for a confirmation containing "Delete this conversation and all its messages?"
    And I should see "Conversation deleted successfully"
    And the team service should have been asked to delete the conversations "conv-1"

  Scenario: Selected conversations are deleted in bulk
    Given 3 team conversations exist
    And deleting a team conversation succeeds
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/conversations"
    And I click "css=#select-all"
    Then I should see "3 selected"
    When I click "Delete selected"
    Then the page should have asked for a confirmation containing "Delete the 3 selected conversation(s)"
    And I should see "3 conversation(s) deleted"
    And the team service should have been asked to delete the conversations "conv-0,conv-1,conv-2"

  Scenario: The bulk actions follow the scopes
    Given 3 team conversations exist
    And I sign in with the scopes "team:read team:write"
    When I navigate to "/team/team-1/conversations"
    Then "Cancel tasks" should be hidden
    When I click "css=.conv-cb"
    Then "Cancel tasks" should be visible
    And "Delete selected" should be hidden

  # --- Memory ---

  Scenario: The memory entries of a team are listed
    Given the team memory holds the entry "Important fact"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/memory"
    Then I should see "Memory Entries (1)"
    And I should see "Important fact"

  Scenario: A memory entry with markup is shown as text
    Given the team memory holds the entry "<img src=x onerror=alert(1)> noted"
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/memory"
    Then I should see "<img src=x onerror=alert(1)> noted"
    And "css=.memory-content img" should be hidden
    And the browser should report no errors

  Scenario: A memory entry is deleted after a confirmation
    Given the team memory holds the entry "Important fact"
    And deleting a team memory entry succeeds
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/memory"
    And I click "Delete" in the page content
    Then the page should have asked for a confirmation containing "Delete this memory entry?"
    And I should see "Memory entry deleted"

  Scenario: Selected memory entries are deleted in bulk
    Given the team memory holds the entry "Important fact"
    And deleting a team memory entry succeeds
    And I sign in with the scopes "team:*"
    When I navigate to "/team/team-1/memory"
    And I click "css=#select-all"
    And I click "Delete selected"
    Then the page should have asked for a confirmation containing "Delete the 1 selected memory entry(ies)?"
    And I should see "1 entry(ies) deleted"
    And the team service should have been asked to delete the memory entries "mem-1"
