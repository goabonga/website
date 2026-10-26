Feature: Database migrations
  As the platform operator
  I want the schema managed by a single linear Alembic history
  So that every environment can be upgraded to the same state

  Scenario: The history has a single head
    Given the Alembic configuration of the application
    Then the migration history should have the single head "014_add_knowledge_status"
    And the migration history should contain 14 revisions

  Scenario: A fresh database receives every application table
    Given the Alembic configuration of the application
    When the upgrade to head is rendered as SQL
    Then the SQL should create the tables:
      | table                 |
      | conversations         |
      | messages              |
      | usage_logs            |
      | anonymous_sessions    |
      | knowledge_base        |
      | knowledge_namespaces  |
      | system_prompts        |
      | system_prompt_versions |

  Scenario: Email tables moved to the mailer service are dropped
    Given the Alembic configuration of the application
    When the upgrade to head is rendered as SQL
    Then the SQL should drop the table "email_templates"
    And the SQL should drop the table "contacts"

  Scenario: The upgrade records the head revision
    Given the Alembic configuration of the application
    When the upgrade to head is rendered as SQL
    Then the SQL should record the revision "014_add_knowledge_status"
