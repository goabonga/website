@browser
Feature: Email templates in a browser
  As an operator with the email template permissions
  I want to design, preview, duplicate and delete email templates
  So that the campaigns have reusable content

  Background:
    Given the templates API returns a list of templates
    And a template exists via API with id 1
    And compiling MJML via API succeeds
    And rendering a template via API succeeds

  # --- Access and sidebar ---

  Scenario: The templates are listed
    Given I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates"
    Then the page title should be "Email Templates - Internal Admin"
    And I should see "Welcome Email"
    And I should see "Welcome %first_name%!"
    And the sidebar menu should highlight only "Email Templates"
    And the browser should report no errors

  Scenario: The Email Templates link leads to the list
    Given I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/1"
    Then the sidebar menu should highlight only "Email Templates"
    When I follow the sidebar link "Email Templates"
    Then the URL should be "/email-templates"

  Scenario: A user without the template scope gets the access denied page
    Given I sign in with the scopes "contacts:read"
    When I navigate to "/email-templates"
    Then the page title should contain "Access Denied"
    And I should see "email_templates:read"

  Scenario: An anonymous visitor comes back to the page asked for after the login
    Given a user holding the scopes "email_templates:*" exists at the provider
    When I navigate to "/email-templates/1"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/email-templates/1"
    And I should see "A welcome email template"

  Scenario: The templates are filtered by status
    Given I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates"
    And I select "Draft" from "status"
    And I click "Filter"
    Then the URL should contain "status=draft"

  Scenario: The search is kept in the address
    Given I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates"
    And I fill "search" with "R&D"
    And I click "Filter"
    Then the URL should contain "search=R%26D"

  # --- Creating ---

  Scenario: A template is created from the visual editor
    Given creating a template via API succeeds
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates"
    And I click "New Template"
    Then the URL should be "/email-templates/new"
    And "Compiled successfully" should be visible
    When I fill "Template Name *" with "Welcome Email"
    And I fill "Email Subject *" with "Welcome %first_name%!"
    And I click "Create Template"
    Then the URL should contain "/email-templates?success="
    And I should see "Template created successfully"
    And the mailler service should have been asked to create the template "Welcome Email"

  Scenario: The slug is derived from the name
    Given I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/new"
    And I fill "Template Name *" with "Big Sale 2024"
    And I press "Tab"
    Then the field "Slug" should contain "big-sale-2024"

  Scenario: A template can be written as MJML code
    Given creating a template via API succeeds
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/new"
    And I fill "Template Name *" with "Code made"
    And I fill "Email Subject *" with "Hello"
    And I click "Code"
    And I fill "css=#mjml-code" with the text '<mjml><mj-body><mj-section><mj-column><mj-text>Custom body</mj-text></mj-column></mj-section></mj-body></mjml>'
    And I click "Create Template"
    Then the URL should contain "/email-templates?success="
    And the template should have been created with the source containing "Custom body"

  Scenario: MJML without its root tag is stopped before it is sent
    Given creating a template via API succeeds
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/new"
    And I fill "Template Name *" with "Broken"
    And I fill "Email Subject *" with "Hello"
    And I click "Code"
    And I fill "css=#mjml-code" with the text '<mj-text>no root</mj-text>'
    And I click "Create Template"
    Then the page should have alerted "Invalid MJML"
    And the URL should be "/email-templates/new"
    And the mailler service should not have been asked to create a template

  Scenario: The live preview reports a compilation error
    Given compiling MJML via API returns errors
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/new"
    Then I should see "Error: Invalid MJML element"

  Scenario: The form requires a name and a subject
    Given creating a template via API succeeds
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/new"
    And I click "Create Template"
    Then the URL should be "/email-templates/new"
    And the mailler service should not have been asked to create a template

  Scenario: A template the mailler service refuses is reported on the form
    Given creating a template via API fails
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/new"
    And I fill "Template Name *" with "Welcome Email"
    And I fill "Email Subject *" with "Hello"
    And I click "Create Template"
    Then the URL should contain "/email-templates/new?error="
    And I should see "Failed to create template"

  # --- Detail and editing ---

  Scenario: The list leads to the detail of a template
    Given I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates"
    And I click "Welcome Email"
    Then the URL should be "/email-templates/1"
    And I should see "VARIABLES USED"
    And I should see "Hello"

  Scenario: A template that does not exist sends the user back to the list
    Given a template does not exist via API
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/404"
    Then the URL should contain "/email-templates?error="
    And I should see "Template not found"

  Scenario: A template is updated from its edit form
    Given updating a template via API succeeds
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/1"
    And I click "Edit Template"
    Then the URL should be "/email-templates/1/edit"
    And the field "Template Name *" should contain "Welcome Email"
    When I fill "Template Name *" with "Updated Template"
    And I click "Update Template"
    Then the URL should contain "/email-templates/1?success="
    And I should see "Template updated successfully"

  Scenario: A template the mailler service cannot update is reported on the form
    Given updating a template via API fails
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/1/edit"
    And I click "Update Template"
    Then I should see "Failed to update template"

  Scenario: A template is duplicated and its copy is opened for editing
    Given duplicating a template via API succeeds
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/1"
    And I click "Duplicate" in the page content
    Then the URL should contain "/email-templates/20/edit?success="
    And I should see "Template duplicated"

  # --- Deleting ---

  Scenario: A template is deleted from its page after a confirmation
    Given deleting a template via API succeeds
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/1"
    And I click "Delete Template"
    Then the page should have asked for a confirmation containing "delete this template"
    And the URL should contain "/email-templates?success="
    And I should see "Template deleted successfully"

  Scenario: A template is deleted from its edit form after a confirmation
    Given deleting a template via API succeeds
    And updating a template via API succeeds
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/1/edit"
    And I click "Delete" in the page content
    Then the page should have asked for a confirmation containing "delete this template"
    And the URL should contain "/email-templates?success="
    And I should see "Template deleted successfully"
    And the mailler service should not have updated the template

  Scenario: A template the mailler service cannot delete is reported
    Given deleting a template via API fails
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates/1"
    And I click "Delete Template"
    Then I should see "Failed to delete template"

  Scenario: Selected templates are deleted in bulk
    Given bulk deleting templates via API succeeds
    And I sign in with the scopes "email_templates:*"
    When I navigate to "/email-templates"
    And I click "css=.row-checkbox"
    And I click "Delete Selected"
    Then the page should have asked for a confirmation containing "delete the selected templ"
    And I should see "template(s) deleted successfully"
