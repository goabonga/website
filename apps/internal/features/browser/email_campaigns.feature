@browser
Feature: Email campaigns in a browser
  As an operator with the email campaign permissions
  I want to prepare, send, pause and delete email campaigns
  So that I can reach the contact groups

  Background:
    Given the campaigns API returns a list of campaigns
    And the campaigns API returns templates and groups for the form
    And a draft campaign exists via API with id 1

  # --- Access and sidebar ---

  Scenario: The campaigns are listed
    Given I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns"
    Then the page title should be "Email Campaigns - Internal Admin"
    And I should see "Newsletter January"
    And the sidebar menu should highlight only "Email Campaigns"
    And the browser should report no errors

  Scenario: The Email Campaigns link leads to the list
    Given I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/1"
    Then the sidebar menu should highlight only "Email Campaigns"
    When I follow the sidebar link "Email Campaigns"
    Then the URL should be "/email-campaigns"

  Scenario: A user without the campaign scope gets the access denied page
    Given I sign in with the scopes "contacts:read"
    When I navigate to "/email-campaigns"
    Then the page title should contain "Access Denied"
    And I should see "email_campaigns:read"

  Scenario: An anonymous visitor comes back to the page asked for after the login
    Given a user holding the scopes "email_campaigns:*" exists at the provider
    When I navigate to "/email-campaigns/1"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/email-campaigns/1"
    And I should see "Draft Campaign"

  Scenario: The campaigns are filtered by status
    Given I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns"
    And I select "Paused" from "status"
    And I click "Filter"
    Then the URL should contain "status=paused"

  Scenario: The search is kept in the address
    Given I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns"
    And I fill "search" with "R&D"
    And I click "Filter"
    Then the URL should contain "search=R%26D"

  # --- Creating ---

  Scenario: A campaign is created from the form
    Given the campaigns API returns templates and groups for the form
    And creating a campaign via API succeeds
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns"
    And I click "New Campaign"
    Then the URL should be "/email-campaigns/new"
    When I fill "Campaign Name *" with "My Campaign"
    And I select "Welcome Template" from "Email Template *"
    And I select "All Subscribers (0 contacts)" from "Contact Group *"
    And I select "Smtp" from "Provider"
    And I click "Create Campaign"
    Then the URL should contain "/email-campaigns/10?success="
    And I should see "Campaign created successfully"
    And the mailler service should have been asked to create the campaign "My Campaign"
    And the created campaign should be sent through the provider "smtp"

  Scenario: The providers are listed by name
    Given the campaigns API returns templates and groups for the form
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/new"
    Then the field "Provider" should offer these options
      | option               |
      | Use default provider |
      | Ses                  |
      | Smtp                 |

  Scenario: The form requires a name, a template and a group
    Given creating a campaign via API succeeds
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/new"
    And I click "Create Campaign"
    Then the URL should be "/email-campaigns/new"
    And the mailler service should not have been asked to create a campaign

  Scenario: A campaign the mailler service refuses is reported on the form
    Given creating a campaign via API fails
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/new"
    And I fill "Campaign Name *" with "My Campaign"
    And I select "Welcome Template" from "Email Template *"
    And I select "All Subscribers (0 contacts)" from "Contact Group *"
    And I click "Create Campaign"
    Then the URL should contain "/email-campaigns/new?error="
    And I should see "Failed to create campaign"

  # --- Detail and editing ---

  Scenario: The list leads to the detail of a campaign
    Given I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns"
    And I click "View"
    Then the URL should be "/email-campaigns/1"
    And I should see "Statistics"
    And I should see "Total Recipients"

  Scenario: A campaign that does not exist sends the user back to the list
    Given a campaign does not exist via API
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/404"
    Then the URL should contain "/email-campaigns?error="
    And I should see "Campaign not found"

  Scenario: A campaign is updated from its edit form
    Given updating a campaign via API succeeds
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/1"
    And I click "Edit" in the page content
    Then the URL should be "/email-campaigns/1/edit"
    When I fill "Campaign Name *" with "Updated Campaign"
    And I click "Update Campaign"
    Then the URL should contain "/email-campaigns/1?success="
    And I should see "Campaign updated successfully"

  Scenario: A campaign the mailler service cannot update is reported on the form
    Given updating a campaign via API fails
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/1/edit"
    And I click "Update Campaign"
    Then I should see "Failed to update campaign"

  Scenario: A campaign that is being sent cannot be edited
    Given a "sending" campaign with 50 emails sent exists via API with id 2
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/2/edit"
    Then the URL should contain "/email-campaigns/2?error="

  # --- Sending ---

  Scenario: A draft campaign is started after a confirmation
    Given sending a campaign via API succeeds
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/1"
    And I click "► Start Campaign"
    Then the page should have asked for a confirmation containing "Start sending this campaign"
    And the URL should contain "/email-campaigns/1?success="
    And I should see "Campaign sending started"

  Scenario: Dismissing the confirmation does not start the campaign
    Given sending a campaign via API succeeds
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/1"
    And I dismiss the next confirmation
    And I click "► Start Campaign"
    Then the URL should be "/email-campaigns/1"
    And the mailler service should not have started the campaign

  Scenario: A sending campaign is paused
    Given a "sending" campaign with 50 emails sent exists via API with id 2
    And pausing a campaign via API succeeds
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/2"
    And I click "Pause"
    Then the URL should contain "/email-campaigns/2?success="
    And I should see "Campaign paused"

  Scenario: A paused campaign is resumed
    Given a "paused" campaign with 30 emails sent exists via API with id 3
    And resuming a campaign via API succeeds
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/3"
    And I click "Resume"
    Then the URL should contain "/email-campaigns/3?success="
    And I should see "Campaign resumed"

  Scenario: A sending campaign cannot be deleted
    Given a "sending" campaign with 50 emails sent exists via API with id 2
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/2"
    Then "Delete Campaign" should be hidden

  # --- Deleting ---

  Scenario: A draft campaign is deleted after a confirmation
    Given deleting a campaign via API succeeds
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns/1"
    And I click "Delete Campaign"
    Then the page should have asked for a confirmation containing "delete this campaign"
    And the URL should contain "/email-campaigns?success="
    And I should see "Campaign deleted successfully"

  Scenario: Selected campaigns are deleted in bulk
    Given bulk delete campaigns via API deletes 1 campaigns
    And I sign in with the scopes "email_campaigns:*"
    When I navigate to "/email-campaigns"
    And I click "css=input[name=campaign_ids]"
    And I click "Delete Selected"
    Then the page should have asked for a confirmation containing "delete 1 campaign(s)"
    And I should see "Deleted 1 campaign(s) successfully"
