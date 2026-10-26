Feature: Stripe service
  Every Stripe object created by the service is tagged with the identifier of
  the SaaS application it belongs to. The Stripe SDK is replaced by a mock, so
  no network call is made.

  Scenario: Products are tagged with the SaaS identifier
    When I create the Stripe product "Pro" for SaaS "saas-1"
    Then the Stripe call metadata should contain "saas_id" with value "saas-1"
    And the Stripe call parameter "name" should be "Pro"

  Scenario: Custom metadata is merged with the SaaS identifier
    When I register the Stripe product "Pro" with metadata "plan=gold" for SaaS "saas-1"
    Then the Stripe call metadata should contain "saas_id" with value "saas-1"
    And the Stripe call metadata should contain "plan" with value "gold"

  Scenario: Callers cannot override the SaaS identifier
    When I register the Stripe product "Pro" with metadata "saas_id=other-saas" for SaaS "saas-1"
    Then the Stripe call metadata should contain "saas_id" with value "saas-1"

  Scenario: Checkout metadata cannot override the SaaS identifier
    When I create a Stripe checkout session for SaaS "saas-1" with metadata "saas_id=other-saas"
    Then the Stripe call metadata should contain "saas_id" with value "saas-1"

  Scenario: Nested metadata is sent to Stripe as strings
    When I create the Stripe product "Pro" for SaaS "saas-1" with the limits document '{"seats": 5}'
    Then the Stripe call metadata should contain "limits" with value '{"seats":5}'

  Scenario: Customers carry the SaaS identifier and the external identifier
    When I create the Stripe customer "user-1" for SaaS "saas-1"
    Then the Stripe call metadata should contain "saas_id" with value "saas-1"
    And the Stripe call metadata should contain "external_id" with value "user-1"

  Scenario: Metered prices are summed over the billing period
    When I create a metered Stripe price for SaaS "saas-1"
    Then the Stripe call metadata should contain "saas_id" with value "saas-1"
    And the Stripe price should aggregate usage with "sum"

  Scenario: Enabled features are appended to the product description
    When I build a description "Great plan" with the features "SSO" and "Audit log"
    Then the description should be
      """
      Great plan

      Features:
      - SSO
      - Audit log
      """
