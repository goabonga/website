Feature: Data model and database migrations
  As an operator
  I want the schema to be versioned by linear migrations
  So that every environment can be upgraded to the same state

  Scenario: The migration history has a single head
    When I load the migration history
    Then the migration history should have a single head "009_custom_domain_service"
    And the migration history should contain 9 revisions

  Scenario: The first migrations render as SQL without a database
    When I render the SQL of the migrations up to "002_multi_tenant_web"
    Then the SQL should create the pgvector extension
    And the SQL should create the table "tenants"
    And the SQL should create the table "collections"
    And the SQL should create the table "documents"
    And the SQL should create the table "tenant_members"

  Scenario: The declared models cover the whole schema
    Then the model metadata should declare the tables
      | table                       |
      | tenants                     |
      | tenant_members              |
      | invitations                 |
      | collections                 |
      | documents                   |
      | usage_records               |
      | user_plans                  |
      | collection_collaborators    |
      | collection_invitations      |
      | workspace_deletion_requests |
      | mcp_releases                |
      | mcp_release_assets          |

  Scenario: A collection owned by a user is personal
    Given a collection owned by a "user"
    Then the collection should be personal
    And the collection should not be organization owned

  Scenario: A collection owned by an organization is shared
    Given a collection owned by a "organization"
    Then the collection should be organization owned

  Scenario: Only enterprise organizations can use custom domains
    Given an organization on the "enterprise" plan
    Then the organization can use a custom domain
    Given an organization on the "free" plan
    Then the organization cannot use a custom domain
