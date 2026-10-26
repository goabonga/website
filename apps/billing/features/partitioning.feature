Feature: Partitioning of the API per SaaS application
  An OAuth client may only act on the SaaS apps it is bound to. Two SaaS
  apps, alpha and beta, each have a plan with the same slug, a price, a
  customer and a subscription. The default test token holds the wildcard
  scope, which includes the admin scope.

  Background:
    Given two SaaS apps "alpha" and "beta" each with a plan, a price, a customer and a subscription
    And the OAuth client "client-alpha" has the scopes "billing:platform:read billing:platform:write billing:usage:write billing:checkout:write"
    And the OAuth client "client-alpha" is bound to the SaaS app "alpha"

  Scenario: A bound client reads the data of its own SaaS app
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a GET to "/platform/{alpha_saas_id}/products"
    Then the response status should be 200
    And the response JSON should be a list of 1 items

  Scenario: A bound client cannot read the products of another SaaS app
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a GET to "/platform/{beta_saas_id}/products"
    Then the response status should be 403

  Scenario: A bound client cannot read a customer of another SaaS app
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a GET to "/platform/{beta_saas_id}/customers/{beta_customer_id}"
    Then the response status should be 403

  Scenario: A bound client cannot cancel a subscription of another SaaS app
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a POST to "/platform/{beta_saas_id}/subscriptions/{beta_subscription_id}/cancel"
    Then the response status should be 403

  Scenario: A refused write leaves the other SaaS app untouched
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a POST to "/platform/{beta_saas_id}/products" with
      """
      {"name": "Intruder", "slug": "intruder"}
      """
    Then the response status should be 403
    And the SaaS app "beta" still has 1 product

  Scenario: A bound client cannot read or change the record of another SaaS app
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a PATCH to "/platform/saas/{beta_saas_id}" with
      """
      {"name": "Renamed by alpha"}
      """
    Then the response status should be 403

  Scenario: A bound client reports usage on its own SaaS app only
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a POST to "/usage/{alpha_saas_id}/report" with
      """
      {"subscription_id": "{alpha_subscription_id}", "quantity": 4}
      """
    Then the response status should be 201
    When I send a POST to "/usage/{beta_saas_id}/report" with
      """
      {"subscription_id": "{beta_subscription_id}", "quantity": 4}
      """
    Then the response status should be 403

  Scenario: A bound client creates checkout sessions for its own SaaS app only
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a POST to "/checkout/session" with
      """
      {
        "saas_id": "{alpha_saas_id}",
        "customer_id": "{alpha_customer_id}",
        "price_id": "{alpha_price_id}",
        "success_url": "https://example.com/ok",
        "cancel_url": "https://example.com/ko"
      }
      """
    Then the response status should be 200
    When I send a POST to "/checkout/session" with
      """
      {
        "saas_id": "{beta_saas_id}",
        "customer_id": "{beta_customer_id}",
        "price_id": "{beta_price_id}",
        "success_url": "https://example.com/ok",
        "cancel_url": "https://example.com/ko"
      }
      """
    Then the response status should be 403

  Scenario: A checkout cannot mix a customer of one SaaS app with a price of another
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a POST to "/checkout/session" with
      """
      {
        "saas_id": "{alpha_saas_id}",
        "customer_id": "{alpha_customer_id}",
        "price_id": "{beta_price_id}",
        "success_url": "https://example.com/ok",
        "cancel_url": "https://example.com/ko"
      }
      """
    Then the response status should be 404

  Scenario: Plans are served for the bound SaaS app only
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a GET to "/plans/alpha"
    Then the response status should be 200
    And the limits of the plan "pro" should be '{"alpha_seats": 1}'
    When I send a GET to "/plans/beta"
    Then the response status should be 404

  Scenario: Two SaaS apps expose their own limits under the same plan slug
    When I send a GET to "/plans/beta"
    Then the response status should be 200
    And the limits of the plan "pro" should be '{"beta_seats": 2}'

  Scenario: A client without binding is denied
    Given the OAuth client "client-new" has the scopes "billing:platform:read"
    And I am authenticated as the OAuth client "client-new"
    When I send a GET to "/platform/{alpha_saas_id}/products"
    Then the response status should be 403

  Scenario: A client without binding sees no SaaS app
    Given the OAuth client "client-new" has the scopes "billing:platform:read"
    And I am authenticated as the OAuth client "client-new"
    When I send a GET to "/platform/saas"
    Then the response status should be 200
    And the response JSON should be an empty list

  Scenario: A bound client lists only its own SaaS app
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a GET to "/platform/saas"
    Then the response status should be 200
    And the response JSON should be a list of 1 items

  Scenario: The admin scope crosses SaaS apps
    Given the OAuth client "client-ops" has the scopes "billing:platform:read billing:admin"
    And I am authenticated as the OAuth client "client-ops"
    When I send a GET to "/platform/{beta_saas_id}/products"
    Then the response status should be 200
    When I send a GET to "/platform/saas"
    Then the response JSON should be a list of 2 items

  Scenario: Only the admin scope can create a SaaS app
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a POST to "/platform/saas" with
      """
      {"name": "Gamma", "slug": "gamma"}
      """
    Then the response status should be 403

  Scenario: A bound client cannot bind itself to another SaaS app
    Given I am authenticated as the OAuth client "client-alpha"
    When I send a PUT to "/platform/saas/{beta_saas_id}/clients/client-alpha"
    Then the response status should be 403

  Scenario: The admin binds a client, then unbinds it
    Given the OAuth client "client-beta" has the scopes "billing:platform:read"
    And I am authenticated as the OAuth client "client-beta"
    When I send a GET to "/platform/{beta_saas_id}/products"
    Then the response status should be 403
    Given I am authenticated
    When I send a PUT to "/platform/saas/{beta_saas_id}/clients/client-beta"
    Then the response status should be 201
    When I send a PUT to "/platform/saas/{beta_saas_id}/clients/client-beta"
    Then the response status should be 200
    Given I am authenticated as the OAuth client "client-beta"
    When I send a GET to "/platform/{beta_saas_id}/products"
    Then the response status should be 200
    Given I am authenticated
    When I send a DELETE to "/platform/saas/{beta_saas_id}/clients/client-beta"
    Then the response status should be 204
    Given I am authenticated as the OAuth client "client-beta"
    When I send a GET to "/platform/{beta_saas_id}/products"
    Then the response status should be 403

  Scenario: The admin lists the bindings of a SaaS app and of a client
    Given I am authenticated
    When I send a GET to "/platform/saas/{alpha_saas_id}/clients"
    Then the response status should be 200
    And the response JSON should be a list of 1 items
    When I send a GET to "/platform/clients/client-alpha/saas"
    Then the response status should be 200
    And the response JSON "client_id" should be "client-alpha"

  Scenario: A token without OAuth client is denied
    Given an access token without OAuth client with the scopes "billing:platform:read"
    And I am authenticated as the OAuth client "no-client"
    When I send a GET to "/platform/{alpha_saas_id}/products"
    Then the response status should be 403
