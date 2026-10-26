Feature: Authorized clients of the mailler service
  As an administrator of the mailler service
  I want to choose which applications may send emails, and with which identity and limits
  So that each application only sends as itself and cannot flood the providers

  Background:
    Given I am a super admin

  # --- List ---

  Scenario: List the clients
    Given the mailler service has the clients "app-one, app-two"
    When I send a GET request to "/mailler/clients"
    Then the response status code should be 200
    And the response should contain "app-one"
    And the response should contain "app-two"
    And the response should contain "no-reply@example.test"
    And the response should contain "60/min"
    And the response should contain "5000/day"

  Scenario: List the clients with a search and a status filter
    Given the mailler service has the clients "app-one"
    When I send a GET request to "/mailler/clients?search=app&status=active&page=1"
    Then the response status code should be 200
    And the response should be HTML

  Scenario: An unknown status filter is refused
    When I send a GET request to "/mailler/clients?status=weird"
    Then the response status code should be 422

  Scenario: List without any client
    Given the mailler service has no client
    When I send a GET request to "/mailler/clients"
    Then the response status code should be 200
    And the response should contain "No clients found."

  Scenario: An inactive client can be activated again
    Given the mailler service has an inactive client "app-one"
    When I send a GET request to "/mailler/clients"
    Then the response status code should be 200
    And the response should contain "/mailler/clients/app-one/activate"
    And the response should not contain "/mailler/clients/app-one/deactivate"

  Scenario: The list needs authentication
    Given I am not authenticated
    When I send a GET request to "/mailler/clients"
    Then the response status code should be 302

  Scenario: The list needs the mailler admin scope
    Given I am authenticated with scopes "mailler:read mailler:write"
    When I send a GET request to "/mailler/clients"
    Then the response status code should be 403

  Scenario: The dashboard links to the clients for administrators only
    Given the mailler stats returns data
    When I send a GET request to "/mailler"
    Then the response should contain "/mailler/clients"

  Scenario: The dashboard hides the clients from other users
    Given I am authenticated with scopes "mailler:read mailler:write"
    And the mailler stats returns data
    When I send a GET request to "/mailler"
    Then the response status code should be 200
    And the response should not contain "/mailler/clients"

  # --- Register ---

  Scenario: View the registration form
    Given the mailler service has the clients "app-one"
    When I send a GET request to "/mailler/clients/new"
    Then the response status code should be 200
    And the response should contain "Register Client"
    And the response should contain "smtp"

  Scenario: Register a client with its sender, providers, limits and callback
    Given the mailler service accepts the client changes
    When I send a POST request to "/mailler/clients/new" with form data
      | field                 | value                           |
      | client_id             | app-two                         |
      | name                  | App two                         |
      | is_active             | true                            |
      | from_email            | no-reply@app-two.example.test   |
      | allowed_providers     | ses                             |
      | default_provider      | ses                             |
      | rate_limit_per_minute | 30                              |
      | daily_quota           | 1000                            |
      | callback_url          | https://app-two.example.test/cb |
      | callback_secret       | 0123456789abcdef                |
    Then the response status code should be 303
    And I should be redirected to "/mailler/clients?success=Client+app-two+registered"
    And the client "app-two" should have been registered with the sender "no-reply@app-two.example.test"
    And the registration should carry a rate limit of 30 per minute and a quota of 1000 per day
    And the registration should allow the providers "ses" with "ses" by default

  Scenario: The service can refuse a registration
    Given the mailler service refuses the client changes with "Client 'app-two' is already registered"
    When I send a POST request to "/mailler/clients/new" with form data
      | field     | value   |
      | client_id | app-two |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/mailler/clients/new?error=Client+%27app-two%27+is+already+registered"

  Scenario: A client id with spaces is not registered
    Given the mailler service accepts the client changes
    When I send a POST request to "/mailler/clients/new" with form data
      | field     | value     |
      | client_id | two words |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/mailler/clients/new?error="
    And no client should have been registered

  Scenario: A limit that is not a positive whole number is not registered
    Given the mailler service accepts the client changes
    When I send a POST request to "/mailler/clients/new" with form data
      | field       | value   |
      | client_id   | app-two |
      | daily_quota | 0       |
    Then the response status code should be 303
    And I should be redirected to a URL containing "must+be+a+positive+whole+number"
    And no client should have been registered

  Scenario: Registering needs the mailler admin scope
    Given I am authenticated with scopes "mailler:read mailler:write"
    And the mailler service accepts the client changes
    When I send a POST request to "/mailler/clients/new" with form data
      | field     | value   |
      | client_id | app-two |
    Then the response status code should be 403
    And no client should have been registered

  # --- Edit ---

  Scenario: View the edit form of a client
    Given the mailler service has the clients "app-one"
    When I send a GET request to "/mailler/clients/app-one/edit"
    Then the response status code should be 200
    And the response should contain "Edit app-one"
    And the response should contain "other@example.test, Other"
    And the response should contain "A secret is set: leave empty to keep it"

  Scenario: Edit the form of an unknown client
    Given the mailler service does not know the client "gone"
    When I send a GET request to "/mailler/clients/gone/edit"
    Then the response status code should be 303
    And I should be redirected to "/mailler/clients?error=Client+not+found"

  Scenario: Emptying the limits of a client removes them
    Given the mailler service accepts the client changes
    When I send a POST request to "/mailler/clients/app-one/edit" with form data
      | field      | value                  |
      | name       | App one                |
      | is_active  | true                   |
      | from_email | no-reply@example.test  |
    Then the response status code should be 303
    And I should be redirected to "/mailler/clients?success=Client+app-one+updated"
    And the client "app-one" should have been updated with no limits

  Scenario: Emptying the callback URL removes the callback and its secret
    Given the mailler service accepts the client changes
    When I send a POST request to "/mailler/clients/app-one/edit" with form data
      | field     | value   |
      | name      | App one |
      | is_active | true    |
    Then the response status code should be 303
    And the client "app-one" should have been updated with the callback removed

  Scenario: The service can refuse an update
    Given the mailler service refuses the client changes with "callback_secret needs a callback_url"
    When I send a POST request to "/mailler/clients/app-one/edit" with form data
      | field     | value   |
      | callback_secret | 0123456789abcdef |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/mailler/clients/app-one/edit?error=callback_secret+needs+a+callback_url"

  Scenario: An invalid limit is not sent when editing
    Given the mailler service accepts the client changes
    When I send a POST request to "/mailler/clients/app-one/edit" with form data
      | field                 | value |
      | rate_limit_per_minute | many  |
    Then the response status code should be 303
    And I should be redirected to a URL containing "/mailler/clients/app-one/edit?error="
    And no client should have been updated

  # --- Deactivate and activate ---

  Scenario: Deactivate a client
    Given the mailler service accepts the client changes
    When I send a POST request to "/mailler/clients/app-one/deactivate"
    Then the response status code should be 303
    And I should be redirected to "/mailler/clients?success=Client+app-one+deactivated"
    And the client "app-one" should have been set inactive

  Scenario: Activate a client again
    Given the mailler service accepts the client changes
    When I send a POST request to "/mailler/clients/app-one/activate"
    Then the response status code should be 303
    And I should be redirected to "/mailler/clients?success=Client+app-one+activated"
    And the client "app-one" should have been set active

  Scenario: Deactivating an unknown client reports the service's answer
    Given the mailler service refuses the client changes with "Client not found"
    When I send a POST request to "/mailler/clients/gone/deactivate"
    Then the response status code should be 303
    And I should be redirected to "/mailler/clients?error=Client+not+found"

  Scenario: Deactivating needs the mailler admin scope
    Given I am authenticated with scopes "mailler:read mailler:write"
    And the mailler service accepts the client changes
    When I send a POST request to "/mailler/clients/app-one/deactivate"
    Then the response status code should be 403
    And no client should have been updated

  # --- Sidebar ---

  Scenario: Sidebar on the clients list
    Given I am authenticated with only the scopes "mailler:* vpn:admin billing:read" granted by token exchange
    And the mailler service has the clients "app-one"
    When I send a GET request to "/mailler/clients"
    Then the response status code should be 200
    And the active sidebar link should be "/mailler"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the registration form
    Given I am authenticated with only the scopes "mailler:* vpn:admin billing:read" granted by token exchange
    And the mailler service has the clients "app-one"
    When I send a GET request to "/mailler/clients/new"
    Then the response status code should be 200
    And the active sidebar link should be "/mailler"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario: Sidebar on the edit form of a client
    Given I am authenticated with only the scopes "mailler:* vpn:admin billing:read" granted by token exchange
    And the mailler service has the clients "app-one"
    When I send a GET request to "/mailler/clients/app-one/edit"
    Then the response status code should be 200
    And the active sidebar link should be "/mailler"
    And the sidebar should link to "/vpn/sessions"
    And the sidebar should link to "/billing"
    And the sidebar should show the user "admin@test.local"

  Scenario Outline: Sidebar gated links follow the scopes on the clients list
    Given I am authenticated with only the scopes "<scopes>" granted by token exchange
    And the mailler service has the clients "app-one"
    When I send a GET request to "/mailler/clients"
    Then the response status code should be 200
    And the sidebar link to "/vpn/sessions" should be <vpn>
    And the sidebar link to "/billing" should be <billing>

    Examples:
      | scopes                           | vpn     | billing |
      | mailler:*                        | hidden  | hidden  |
      | mailler:* vpn:admin              | visible | hidden  |
      | mailler:* billing:read           | hidden  | visible |
      | mailler:* vpn:admin billing:read | visible | visible |
      | *                                | visible | visible |
