Feature: Email delivery through mailler
  As the platform
  I want every email to be sent by the mailler service from templates I ship
  So that senders, providers and rendering are managed in one place

  Scenario Outline: Every shipped template can be imported into mailler
    Given the shipped "<template>" email template
    Then the template should have a source and a description for mailler
    And the template should use "workspace_name", "user_email" and "year"

    Examples:
      | template                      |
      | workspace_invitation          |
      | workspace_deletion            |
      | workspace_deletion_reminder   |
      | workspace_deletion_scheduled  |
      | workspace_deleted             |

  Scenario: The import command is given the template directory
    When I ask for the template directory
    Then it should contain the 5 templates

  Scenario: An email is sent from a template of the application
    Given a mailler service that accepts emails
    When the application sends the "workspace_invitation" template to "bob@example.test" with the key "task-1"
    Then the email should be accepted
    And mailler should have received a "client_credentials" token request for the scope "mailler:send"
    And mailler should have received the template "workspace_invitation" for "bob@example.test" with the variable "workspace_name" set to "Acme"
    And the request should carry the idempotency key "task-1"
    And the request should not name a sender, a provider or a subject

  Scenario: Variables the template needed but did not get are reported
    Given a mailler service that reports the missing variable "role"
    When the application sends the "workspace_invitation" template to "bob@example.test" with the key "task-2"
    Then the email should be accepted
    And the missing variables should be "role"

  Scenario Outline: Mailler refuses the email
    Given a mailler service that answers <status> "<detail>"
    When the application tries to send the "workspace_invitation" template to "bob@example.test"
    Then the email should be refused with <status>
    And sending again <verdict>

    Examples:
      | status | detail                              | verdict            |
      | 403    | Client not authorized               | cannot work        |
      | 404    | Template 'workspace_invitation' not found | cannot work   |
      | 422    | Template is not active              | cannot work        |
      | 429    | Daily quota reached                 | can work           |
      | 503    | Service unavailable                 | can work           |

  Scenario: Mailler cannot be reached
    Given a mailler service that is down
    When the application tries to send the "workspace_invitation" template to "bob@example.test"
    Then the email should be refused without a status
    And sending again can work

  Scenario: Mailler is not configured
    Given no mailler service is configured
    When the application tries to send the "workspace_invitation" template to "bob@example.test"
    Then the email should be refused without a status
    And sending again cannot work
