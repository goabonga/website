Feature: Custom domains
  As an Enterprise customer
  I want to serve my workspace on my own domain
  So that my team uses an address under our own name

  Scenario Outline: Domain validation
    Then the domain "<domain>" should be <verdict>

    Examples:
      | domain            | verdict  |
      | docs.acme.test    | accepted |
      | not a domain      | rejected |
      | localhost         | rejected |
      | printer.local     | rejected |
      | -bad.acme.test    | rejected |

  Scenario Outline: Statuses of the custom-domain service
    Then the status "<service>" of the service should be recorded as "<recorded>"

    Examples:
      | service          | recorded         |
      | pending          | pending          |
      | dns_verifying    | dns_verifying    |
      | dns_verified     | dns_verified     |
      | ssl_provisioning | ssl_provisioning |
      | active           | active           |
      | failed           | failed           |
      | suspended        | failed           |
      | expired          | failed           |
      | deprovisioning   | not recorded     |

  Scenario: A domain is registered in the service for a workspace
    Given the custom-domain service accepts registrations with the CNAME target "apps.example.test"
    When the workspace "acme" registers the domain "docs.acme.test"
    Then the service should have been asked to register "docs.acme.test" for the workspace "acme"
    And the request should not name an upstream, a CNAME target or a certificate
    And the registration should return the CNAME target "apps.example.test"

  Scenario: The service refuses a name that is already registered
    Given the custom-domain service answers 409 "Domain already registered"
    When the workspace "acme" tries to register the domain "docs.acme.test"
    Then the registration should be refused with 409 "Domain already registered"

  Scenario: The service is not configured
    Given no custom-domain service is configured
    When the workspace "acme" tries to register the domain "docs.acme.test"
    Then the registration should be refused without a status

  Scenario: The verification of a domain is restarted
    Given the custom-domain service restarts verifications
    When the verification of the domain "svc-1" is restarted
    Then the new status should be "dns_verifying"

  Scenario: A domain is removed from the service
    Given the custom-domain service removes domains
    When the domain "svc-1" is deleted
    Then the service should have been asked to delete "svc-1"

  Scenario: Deleting a domain the service forgot is not an error
    Given the custom-domain service does not know the domain
    When the domain "svc-1" is deleted
    Then nothing should be left to delete

  Scenario: A signed notification activates the domain
    Given an organization with the custom domain "docs.acme.test" in status "ssl_provisioning"
    And the custom domain webhook secret is "s3cret-of-at-least-thirty-two-characters"
    When the service sends a signed "domain.active" notification
    Then the response status code should be 200
    And the domain status should be "active"

  Scenario: A failure notification carries the reason
    Given an organization with the custom domain "docs.acme.test" in status "dns_verifying"
    And the custom domain webhook secret is "s3cret-of-at-least-thirty-two-characters"
    When the service sends a signed "domain.failed" notification with the error "CNAME not found"
    Then the domain status should be "failed"
    And the domain error should mention "CNAME not found"

  Scenario: A deletion notification forgets the domain
    Given an organization with the custom domain "docs.acme.test" in status "active"
    And the custom domain webhook secret is "s3cret-of-at-least-thirty-two-characters"
    When the service sends a signed "domain.deleted" notification
    Then the organization should have no custom domain

  Scenario: A delivery is applied once
    Given an organization with the custom domain "docs.acme.test" in status "ssl_provisioning"
    And the custom domain webhook secret is "s3cret-of-at-least-thirty-two-characters"
    When the service sends a signed "domain.active" notification
    And the domain status is set back to "ssl_provisioning"
    And the service sends the same notification again
    Then the response should say the delivery is a duplicate
    And the domain status should be "ssl_provisioning"

  Scenario: A captured notification cannot be played back later
    Given an organization with the custom domain "docs.acme.test" in status "ssl_provisioning"
    And the custom domain webhook secret is "s3cret-of-at-least-thirty-two-characters"
    When a notification signed 1 hour ago is played back
    Then the response status code should be 401
    And the domain status should be "ssl_provisioning"

  Scenario: A forged notification is refused
    Given an organization with the custom domain "docs.acme.test" in status "ssl_provisioning"
    And the custom domain webhook secret is "s3cret-of-at-least-thirty-two-characters"
    When a notification signed with another secret is received
    Then the response status code should be 401
    And the domain status should be "ssl_provisioning"

  Scenario: Notifications are refused until a secret is configured
    Given an organization with the custom domain "docs.acme.test" in status "ssl_provisioning"
    And no custom domain webhook secret is configured
    When the service sends a signed "domain.active" notification
    Then the response status code should be 503

  Scenario: The reconciliation registers the domains the service does not know
    Given an organization with the custom domain "docs.acme.test" not yet registered in the service
    And the custom-domain service accepts registrations with the CNAME target "apps.example.test"
    When the reconciliation task runs
    Then the domain "docs.acme.test" should have been registered
    And the organization should be linked to the service domain

  Scenario: The reconciliation refreshes the domains being set up
    Given an organization linked to the service domain "svc-1" with the custom domain "docs.acme.test" in status "ssl_provisioning"
    And the service reports the domain "svc-1" as "active"
    When the reconciliation task runs
    Then the domain status should be "active"
