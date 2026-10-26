Feature: Checkout URL allow-list and branding of billing SaaS apps
  As an administrator of the billing platform
  I want to declare where each SaaS app may send its customers back to, and how its checkout looks
  So that Stripe only redirects to URLs the app accepts

  Background:
    Given I am a super admin

  @billing-checkout-urls
  Scenario: The new SaaS app form offers the allow-list and the branding
    When I send a GET request to "/billing/saas/new"
    Then the response status code should be 200
    And the response should contain "Checkout URL allow-list"
    And the response should contain "Branding (JSON)"

  @billing-checkout-urls
  Scenario: Create a SaaS app with a checkout URL allow-list and a branding
    Given the billing service saves the SaaS app
    When I send a POST request to "/billing/saas/new" with form data
      | field          | value                                                |
      | name           | My SaaS                                              |
      | slug           | my-saas                                              |
      | checkout_urls  | https://app.example.test                             |
      | branding_json  | {"locale": "xx"}                                     |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success="
    And the SaaS app should have been created with the checkout URLs "https://app.example.test"
    And the SaaS app should have been created with the branding '{"locale": "xx"}'

  @billing-checkout-urls
  Scenario: A checkout URL without scheme is refused
    Given the billing service saves the SaaS app
    When I send a POST request to "/billing/saas/new" with form data
      | field         | value           |
      | name          | My SaaS         |
      | slug          | my-saas         |
      | checkout_urls | app.example.test |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/billing/saas/new?error="
    And no SaaS app should have been created

  @billing-checkout-urls
  Scenario: A checkout URL with a query string is refused
    Given the billing service saves the SaaS app
    When I send a POST request to "/billing/saas/saas-1/edit" with form data
      | field         | value                           |
      | name          | My SaaS                         |
      | checkout_urls | https://app.example.test/?utm=1 |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/billing/saas/saas-1/edit?error="
    And no SaaS app should have been updated

  @billing-checkout-urls
  Scenario: A branding that is not a JSON object is refused
    Given the billing service saves the SaaS app
    When I send a POST request to "/billing/saas/new" with form data
      | field         | value   |
      | name          | My SaaS |
      | slug          | my-saas |
      | branding_json | [1, 2]  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "error=Branding+must+be+a+JSON+object"
    And no SaaS app should have been created

  @billing-checkout-urls
  Scenario: The edit form shows the current allow-list and branding
    Given the SaaS app "saas-1" accepts the checkout URLs "https://a.example.test,https://b.example.test/pay" and has the branding '{"locale": "xx"}'
    When I send a GET request to "/billing/saas/saas-1/edit"
    Then the response status code should be 200
    And the response should contain "https://b.example.test/pay"
    And the response should contain "locale"

  @billing-checkout-urls
  Scenario: Emptying the fields on the edit form clears them
    Given the billing service saves the SaaS app
    When I send a POST request to "/billing/saas/saas-1/edit" with form data
      | field         | value   |
      | name          | My SaaS |
      | is_active     | true    |
    Then the response status code should be 303
    And I should be redirected to a URL containing "success="
    And the SaaS app should have been updated with no checkout URL and no branding

  @billing-checkout-urls
  Scenario: The SaaS app page shows the allow-list and the branding
    Given the SaaS app "saas-1" accepts the checkout URLs "https://a.example.test" and has the branding '{"locale": "xx"}'
    When I send a GET request to "/billing/saas/saas-1"
    Then the response status code should be 200
    And the response should contain "https://a.example.test"
    And the response should contain "locale"

  @billing-checkout-urls
  Scenario: The SaaS app page says when redirects are refused
    Given the SaaS app "saas-1" has no checkout URL and no branding
    When I send a GET request to "/billing/saas/saas-1"
    Then the response status code should be 200
    And the response should contain "checkout and portal redirects are refused"
