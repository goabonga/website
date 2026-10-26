@browser
Feature: Custom domain settings pages in a browser
  As an administrator of an Enterprise workspace
  I want to attach my own domain to the workspace
  So that my team reaches the application on our address

  Background:
    Given a user "Alice" who holds every knowledge scope

  Scenario: The settings of an Enterprise workspace lead to the custom domain page
    Given "Alice" owns the workspace "Acme" on the "enterprise" plan
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/settings"
    Then I should see "Enterprise Features"
    When I click "Configure"
    Then the URL should be "/organizations/domain"
    And I should see "Domain Configuration"
    And the sidebar item "General" should be the active one

  Scenario: A domain is registered in the custom-domain service
    Given "Alice" owns the workspace "Acme" on the "enterprise" plan
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/domain"
    And I fill "Custom Domain" with "Docs.Example.Test"
    And I click "Save Domain"
    Then I should see "Provisioning Status"
    And I should see "docs.example.test"
    And I should see "Pending"
    And I should see "cname.example.invalid"
    And the custom-domain service registered "docs.example.test" for the workspace "Acme"

  Scenario: The verification of the DNS can be retried
    Given "Alice" owns the workspace "Acme" on the "enterprise" plan
    And the workspace "Acme" is registered with the domain "docs.example.test" in the custom-domain service
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/domain"
    And I click "Retry DNS Verification"
    Then I should see "Dns Verifying"
    And the custom-domain service verified the domain of the workspace

  Scenario: An active domain is shown with its address
    Given "Alice" owns the workspace "Acme" on the "enterprise" plan
    And the workspace "Acme" is registered with the domain "docs.example.test" in the custom-domain service
    And the custom-domain service reports the domain of the workspace as active
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/domain"
    Then I should see "Your custom domain is active!"
    And the page links "https://docs.example.test" to "https://docs.example.test"

  Scenario: The domain is removed
    Given "Alice" owns the workspace "Acme" on the "enterprise" plan
    And the workspace "Acme" is registered with the domain "docs.example.test" in the custom-domain service
    And the browser accepts the confirmation dialogs
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/domain"
    And I click "Remove Domain"
    Then I should not see "Provisioning Status"
    And the custom-domain service deleted the domain of the workspace

  Scenario: A badly formed domain is refused
    Given "Alice" owns the workspace "Acme" on the "enterprise" plan
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/domain"
    And I fill "Custom Domain" with "not a domain"
    And I click "Save Domain"
    Then I should see "domain"
    And the custom-domain service registered nothing

  Scenario: A domain of another workspace is refused
    Given "Alice" owns the workspace "Acme" on the "enterprise" plan
    And the workspace "Other" already uses the domain "taken.example.test"
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/domain"
    And I fill "Custom Domain" with "taken.example.test"
    And I click "Save Domain"
    Then I should see "This domain is already in use by another organization."

  Scenario: The service refusing a domain is explained
    Given "Alice" owns the workspace "Acme" on the "enterprise" plan
    And the custom-domain service refuses every registration with 409
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/domain"
    And I fill "Custom Domain" with "docs.example.test"
    And I click "Save Domain"
    Then I should see "This domain is already registered."

  Scenario: A service that is down is reported without losing the page
    Given "Alice" owns the workspace "Acme" on the "enterprise" plan
    And the custom-domain service is unavailable
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/domain"
    And I fill "Custom Domain" with "docs.example.test"
    And I click "Save Domain"
    Then I should see "The custom domain service is not available right now."
    And I should see "Domain Configuration"

  Scenario: Only Enterprise workspaces can use a custom domain
    Given "Alice" owns the workspace "Acme" on the "pro" plan
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/domain"
    Then the URL should be "/organizations/settings"
    And I should not see "Enterprise Features"

  Scenario: A regular member cannot configure the domain
    Given a user "Bob" who holds every knowledge scope
    And "Bob" is a member of the workspace "Acme" on the "enterprise" plan
    And I have signed in as "Bob" through the identity provider
    When I navigate to "/tenants/domain"
    Then I should see "You don't have permission to access this resource."

  Scenario: The custom domain pages only lead to pages that exist
    Given "Alice" owns the workspace "Acme" on the "enterprise" plan
    And the workspace "Acme" is registered with the domain "docs.example.test" in the custom-domain service
    And I have signed in as "Alice" through the identity provider
    When I navigate to "/tenants/settings"
    Then every link of the page leads to a page of the application
    When I navigate to "/tenants/domain"
    Then every link of the page leads to a page of the application
