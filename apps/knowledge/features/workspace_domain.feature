Feature: Workspace custom domain settings
  As an administrator of an Enterprise workspace
  I want to attach my own domain to the workspace
  So that my team reaches it under our own name

  Background:
    Given the workspace database is in memory
    And the custom-domain service is in memory

  Scenario: Administrators of an Enterprise workspace see the domain page
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    When I open "/organizations/domain"
    Then the response status code should be 200
    And the page should say "domain"

  Scenario: Other plans are sent back to the settings
    Given I am the owner of the workspace "Acme" on the "pro" plan
    When I open "/organizations/domain"
    Then the response status code should be 302
    And I should be redirected to "/organizations/settings"

  Scenario: Regular members cannot see the domain page
    Given I am a regular member of the workspace "Acme" on the "enterprise" plan
    When I open "/organizations/domain"
    Then the response status code should be 403

  Scenario: Setting a domain registers it in the custom-domain service
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    When I set the custom domain to " Docs.Acme.Test "
    Then the response status code should be 302
    And I should be redirected to "/organizations/domain"
    And the workspace should have the custom domain "docs.acme.test" in status "pending"
    And the service should have registered "docs.acme.test" for the workspace
    And the workspace should be linked to the service domain with the CNAME target "apps.example.test"

  Scenario: Replacing the domain removes the previous one from the service
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    And the domain "old.acme.test" of the workspace is registered in the service as "svc-old" in status "active"
    When I set the custom domain to "docs.acme.test"
    Then the service should have deleted "svc-old"
    And the workspace should have the custom domain "docs.acme.test" in status "pending"

  Scenario: The service refuses the domain
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    And the custom-domain service refuses registrations with 409
    When I set the custom domain to "docs.acme.test"
    Then the response status code should be 200
    And the page should say "already registered"
    And the workspace should have no custom domain

  Scenario: The service is down
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    And the custom-domain service is down
    When I set the custom domain to "docs.acme.test"
    Then the page should say "not available right now"
    And the workspace should have no custom domain

  Scenario: An invalid domain is refused
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    When I set the custom domain to "not a domain"
    Then the response status code should be 200
    And the page should say "Invalid domain format"
    And the service should not have been called

  Scenario: A domain used by another workspace is refused
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    And another workspace already uses the domain "docs.acme.test"
    When I set the custom domain to "docs.acme.test"
    Then the page should say "already in use by another organization"
    And the service should not have been called

  Scenario: The status endpoint reports that there is no domain
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    When I open "/organizations/domain/status"
    Then the response status code should be 200
    And the response JSON "has_domain" should be "False"

  Scenario: The status endpoint reports the provisioning progress
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    And the workspace has the custom domain "docs.acme.test" in status "ssl_provisioning"
    When I open "/organizations/domain/status"
    Then the response JSON "domain" should be "docs.acme.test"
    And the response JSON "status" should be "ssl_provisioning"

  Scenario: Retrying the verification asks the service
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    And the domain "docs.acme.test" of the workspace is registered in the service as "svc-1" in status "failed"
    When I retry the domain verification
    Then the service should have restarted the verification of "svc-1"
    And the workspace should have the custom domain "docs.acme.test" in status "dns_verifying"

  Scenario: Retrying registers a domain the service never knew
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    And the workspace has the custom domain "docs.acme.test" in status "active"
    When I retry the domain verification
    Then the service should have registered "docs.acme.test" for the workspace

  Scenario: Removing the domain clears it and asks the service to remove it
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    And the domain "docs.acme.test" of the workspace is registered in the service as "svc-1" in status "active"
    When I remove the custom domain
    Then the response status code should be 302
    And the workspace should have no custom domain
    And the service should have deleted "svc-1"

  Scenario: The domain is kept when the service cannot remove it
    Given I am the owner of the workspace "Acme" on the "enterprise" plan
    And the domain "docs.acme.test" of the workspace is registered in the service as "svc-1" in status "active"
    And the custom-domain service is down
    When I remove the custom domain
    Then the page should say "not available right now"
    And the workspace should have the custom domain "docs.acme.test" in status "active"
