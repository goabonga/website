Feature: Billing integration
  As the operator of a SaaS platform
  I want plans to follow the subscriptions managed by the billing service
  So that customers get the limits they pay for

  Background:
    Given an organization "cccccccc-cccc-cccc-cccc-cccccccccccc" on the "free" plan
    And this application is the SaaS "saas-of-knowledge" in billing

  Scenario: An active subscription upgrades the organization
    Given the webhook secret is "s3cret"
    When the billing service sends a signed "subscription.updated" event for plan "pro" with status "active"
    Then the response status code should be 200
    And the organization should be on the "pro" plan

  Scenario: The plan is identified by its slug, not by its name
    Given the webhook secret is "s3cret"
    When the billing service sends a signed "subscription.updated" event of the plan named "Pro" with slug "starter" and status "active"
    Then the organization should be on the "starter" plan

  Scenario: A canceled subscription downgrades the organization
    Given the organization is on the "pro" plan
    And the webhook secret is "s3cret"
    When the billing service sends a signed "subscription.updated" event for plan "pro" with status "canceled"
    Then the response status code should be 200
    And the organization should be on the "free" plan

  Scenario: A deleted subscription downgrades the organization
    Given the organization is on the "starter" plan
    And the webhook secret is "s3cret"
    When the billing service sends a signed "subscription.deleted" event for plan "starter" with status "canceled"
    Then the organization should be on the "free" plan

  Scenario: A past due subscription keeps the current plan
    Given the organization is on the "pro" plan
    And the webhook secret is "s3cret"
    When the billing service sends a signed "subscription.updated" event for plan "pro" with status "past_due"
    Then the organization should be on the "pro" plan

  Scenario: An unknown plan slug leaves the plan unchanged
    Given the webhook secret is "s3cret"
    When the billing service sends a signed "subscription.created" event for plan "platinum" with status "active"
    Then the response status code should be 200
    And the organization should be on the "free" plan

  Scenario: An event is applied once even when billing sends it twice
    Given the webhook secret is "s3cret"
    When the billing service sends a signed "subscription.updated" event for plan "pro" with status "active"
    And the organization is on the "free" plan
    And the billing service sends the same event again
    Then the response should say the event is a duplicate
    And the organization should be on the "free" plan

  Scenario: An event for another SaaS application is refused
    Given the webhook secret is "s3cret"
    When the billing service sends a signed event of the SaaS "another-saas" for plan "pro" with status "active"
    Then the response status code should be 400
    And the organization should be on the "free" plan

  Scenario: A bad signature is rejected
    Given the webhook secret is "s3cret"
    When the billing service sends an event signed with the wrong secret
    Then the response status code should be 401
    And the organization should be on the "free" plan

  Scenario: A missing signature is rejected
    Given the webhook secret is "s3cret"
    When the billing service sends an unsigned event
    Then the response status code should be 401

  Scenario: A malformed payload is rejected
    Given the webhook secret is "s3cret"
    When the billing service sends a signed payload that is not an event
    Then the response status code should be 400

  Scenario: Nothing is accepted when no secret is configured
    Given no webhook secret is configured
    When the billing service sends an unsigned event for plan "pro" with status "active"
    Then the response status code should be 503
    And the organization should be on the "free" plan

  Scenario: Nothing is accepted when the SaaS application is not configured
    Given the webhook secret is "s3cret"
    And this application has no SaaS id in billing
    When the billing service sends a signed "subscription.updated" event for plan "pro" with status "active"
    Then the response status code should be 503
    And the organization should be on the "free" plan

  Scenario: Plans are fetched from the billing API and sorted
    Given the billing API lists the plans "Pro" (order 2) and "Free" (order 1)
    When the application loads the plans
    Then the plans should be, in order, "Free", "Pro"

  Scenario: Plan prices are formatted for display
    Given the billing API lists the plans "Pro" (order 2) and "Free" (order 1)
    When the application loads the plans
    Then the plan "Pro" should cost "29" per month and "290" per year
    And the plan "Pro" should save 17 percent when billed yearly
    And the plan "Free" should be free

  Scenario: Plans are requested with a token for the application slug
    Given the billing API lists the plans "Pro" (order 2) and "Free" (order 1)
    When the application loads the plans
    Then the billing API should have been asked for the plans of "my-app" with a bearer token

  Scenario: The limits keep the names chosen by the application
    Given the billing API lists the plans "Pro" (order 2) and "Free" (order 1)
    When the application loads the plans
    Then the plan "Pro" should have the limit "max_seats" set to 10

  Scenario: Plans are cached after the first fetch
    Given the billing API lists the plans "Pro" (order 2) and "Free" (order 1)
    When the application loads the plans
    And the application loads the plans
    Then the billing API should have been called 1 time

  Scenario: A billing API failure is reported
    Given the billing API is failing
    When the application tries to load the plans
    Then loading the plans should fail with a billing error

  Scenario: Without billing configuration there are no plans
    Given the billing API is not configured
    When the application loads the plans
    Then there should be no plans

  Scenario: A checkout is created for the configured SaaS application
    Given the billing API accepts checkout sessions
    When the application starts a checkout for the tenant "tenant-1"
    Then the checkout request should carry the SaaS id "saas-of-knowledge" and the configured URLs

  Scenario: A checkout cannot start without a SaaS id
    Given the billing API accepts checkout sessions
    And this application has no SaaS id in billing
    When the application tries to start a checkout for the tenant "tenant-1"
    Then loading the plans should fail with a billing error
