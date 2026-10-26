@browser
Feature: Authorized clients of the mailler service in a browser
  As an administrator of the mailler service
  I want to choose which applications may send emails, and with which identity and limits
  So that each application only sends as itself and cannot flood the providers

  # --- Access and sidebar ---

  Scenario: The clients are listed with their sender and limits
    Given the mailler service has the clients "app-one, app-two"
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients"
    Then the page title should be "Clients - Mailler - Internal Admin"
    And I should see "app-one"
    And I should see "app-two"
    And I should see "no-reply@example.test"
    And I should see "60/min"
    And I should see "5000/day"
    And I should see "Showing 2 of 2 clients"
    And the sidebar menu should highlight only "Mailler Stats"
    And the browser should report no errors

  Scenario: The dashboard links to the clients for administrators
    Given the mailler stats returns data
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler"
    And I click "Clients →"
    Then the URL should be "/mailler/clients"

  Scenario: The dashboard hides the clients from other users
    Given the mailler stats returns data
    And I sign in with the scopes "mailler:read mailler:write"
    When I navigate to "/mailler"
    Then I should see "Daily Email Volume"
    And I should not see "Clients →"

  Scenario: The list needs the mailler admin scope
    Given the mailler service has the clients "app-one"
    And I sign in with the scopes "mailler:read mailler:write"
    When I navigate to "/mailler/clients"
    Then the page title should contain "Access Denied"
    And I should see "mailler:admin"
    And I should not see "app-one"

  Scenario: An anonymous visitor comes back to the list after the login
    Given the mailler service has the clients "app-one"
    And a user holding the scopes "mailler:*" exists at the provider
    When I navigate to "/mailler/clients?search=app&status=active"
    Then I should be asked to sign in at the provider
    When I sign in at the provider
    Then the URL should be "/mailler/clients?search=app&status=active"
    And I should see "app-one"

  Scenario: The list says when there is no client
    Given the mailler service has no client
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients"
    Then I should see "No clients found."

  Scenario: The clients are searched and filtered by status
    Given the mailler service has the clients "app-one"
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients"
    And I fill "Search:" with "R&D"
    And I select "Active" from "Status:"
    And I click "Filter"
    Then the URL should contain "search=R%26D"
    And the URL should contain "status=active"

  # --- Registering ---

  Scenario: A client is registered with its sender, providers, limits and callback
    Given the mailler service accepts the client changes
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients"
    And I click "+ Register Client"
    Then the URL should be "/mailler/clients/new"
    When I fill "OAuth client ID *" with "app-two"
    And I fill "Name" with "App two"
    And I fill "Default sender address" with "no-reply@app-two.example.test"
    And I click "css=input[name=allowed_providers][value=ses]"
    And I select "ses" from "Default provider"
    And I fill "Emails per minute" with "30"
    And I fill "Emails per day (UTC)" with "1000"
    And I fill "Callback URL" with "https://app-two.example.test/cb"
    And I fill "Callback secret" with "0123456789abcdef"
    And I click "Register Client" in the page content
    Then the URL should contain "/mailler/clients?success="
    And I should see "Client app-two registered"
    And the client "app-two" should have been registered with the sender "no-reply@app-two.example.test"
    And the registration should carry a rate limit of 30 per minute and a quota of 1000 per day
    And the registration should allow the providers "ses" with "ses" by default

  Scenario: The service can refuse a registration and its answer is shown on the form
    Given the mailler service refuses the client changes with "Client 'app-two' is already registered"
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients/new"
    And I fill "OAuth client ID *" with "app-two"
    And I click "Register Client" in the page content
    Then the URL should contain "/mailler/clients/new?error="
    And I should see "Client 'app-two' is already registered"

  Scenario: A client id with spaces is stopped by the form
    Given the mailler service accepts the client changes
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients/new"
    And I fill "OAuth client ID *" with "two words"
    And I click "Register Client" in the page content
    Then the URL should be "/mailler/clients/new"
    And no client should have been registered

  Scenario: A limit that is not a positive whole number is stopped by the form
    Given the mailler service accepts the client changes
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients/new"
    And I fill "OAuth client ID *" with "app-two"
    And I fill "Emails per day (UTC)" with "0"
    And I click "Register Client" in the page content
    Then the URL should be "/mailler/clients/new"
    And no client should have been registered

  # --- Editing ---

  Scenario: The edit form shows the record of the client
    Given the mailler service has the clients "app-one"
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients"
    And I click "Edit"
    Then the URL should be "/mailler/clients/app-one/edit"
    And the field "Default sender address" should contain "no-reply@example.test"
    And the field "Other sender identities" should contain "other@example.test, Other"
    And the field "Callback secret" should have the placeholder "A secret is set: leave empty to keep it"

  Scenario: The form of an unknown client sends the user back to the list
    Given the mailler service does not know the client "gone"
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients/gone/edit"
    Then the URL should contain "/mailler/clients?error="
    And I should see "Client not found"

  Scenario: Emptying the limits of a client removes them
    Given the mailler service has the clients "app-one"
    And the mailler service accepts the client changes
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients/app-one/edit"
    And I clear "Emails per minute"
    And I clear "Emails per day (UTC)"
    And I click "Save Changes"
    Then the URL should contain "/mailler/clients?success="
    And I should see "Client app-one updated"
    And the client "app-one" should have been updated with no limits

  Scenario: Emptying the callback URL removes the callback and its secret
    Given the mailler service has the clients "app-one"
    And the mailler service accepts the client changes
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients/app-one/edit"
    And I clear "Callback URL"
    And I click "Save Changes"
    Then the client "app-one" should have been updated with the callback removed

  Scenario: The service can refuse an update and its answer is shown on the form
    Given the mailler service has the clients "app-one"
    And the mailler service refuses the client changes with "callback_secret needs a callback_url"
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients/app-one/edit"
    And I click "Save Changes"
    Then the URL should contain "/mailler/clients/app-one/edit?error="
    And I should see "callback_secret needs a callback_url"

  # --- Deactivating and activating ---

  Scenario: A client is deactivated after a confirmation
    Given the mailler service has the clients "app-one"
    And the mailler service accepts the client changes
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients"
    And I click "Deactivate"
    Then the page should have asked for a confirmation containing "Deactivate this client?"
    And the URL should contain "/mailler/clients?success="
    And I should see "Client app-one deactivated"
    And the client "app-one" should have been set inactive

  Scenario: Dismissing the confirmation keeps the client active
    Given the mailler service has the clients "app-one"
    And the mailler service accepts the client changes
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients"
    And I dismiss the next confirmation
    And I click "Deactivate"
    Then the URL should be "/mailler/clients"
    And no client should have been updated

  Scenario: An inactive client is activated again
    Given the mailler service has an inactive client "app-one"
    And the mailler service accepts the client changes
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients"
    And I click "Activate"
    Then I should see "Client app-one activated"
    And the client "app-one" should have been set active

  Scenario: The answer of the service is shown when a client cannot be deactivated
    Given the mailler service has the clients "app-one"
    And the mailler service refuses the client changes with "Client not found"
    And I sign in with the scopes "mailler:*"
    When I navigate to "/mailler/clients"
    And I click "Deactivate"
    Then I should see "Client not found"
