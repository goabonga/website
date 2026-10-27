@browser
Feature: Device authorization and pushed authorization requests in a browser
    As the user of a device without a keyboard or of a client that pushes its requests
    I want to approve the request on the pages of the authorization server
    So that the device or the client receives tokens without my password ever leaving the browser

    Background:
        Given an empty user database
        And outgoing e-mails are captured
        And a signing key store protected by a fresh encryption key
        And the operator generated and activated a signing key
        And the application is served at its public address
        And the platform tenant "platform" exists
        And a verified user "alice@example.com" with the password "Sup3r!secret"
        And a public client "tv" for the device flow with the scopes "openid profile"
        And the device polling interval is 0 seconds

    Scenario: A device is approved by scanning the verification link
        Given the device requested a device code from the application for the scopes "openid"
        Then the verification address is served by the application
        When the user scans the verification link of the device
        Then the URL should contain "/auth/login?next="
        When I sign in as "alice@example.com" with the password "Sup3r!secret"
        Then the page title should be "Device Authorization"
        And the field "Device Code" shows the code of the device
        When I click "Continue"
        Then the page title should contain "Authorize Device"
        And I should see "A device is requesting access to your account."
        And the code of the device is displayed on the consent page
        When I click "Allow"
        Then I should see "Authorization Complete"
        When the device polls the application
        Then the response status is 200
        And the token response contains an access token

    Scenario: The code of the device can be typed on the verification page
        Given the device requested a device code from the application for the scopes "openid"
        And a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        When the user opens the verification address of the device
        And the user types the code of the device
        And I click "Continue"
        Then I should see "A device is requesting access to your account."

    Scenario: A wrong code is explained on the verification page
        Given a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        When I navigate to "/oauth2/device/verify"
        And I fill "Device Code" with "ZZZZ-9999"
        And I click "Continue"
        Then I should see "Invalid code. Please check and try again."
        And "Device Code" should be visible

    Scenario: Denying the device tells the user and the device never gets tokens
        Given the device requested a device code from the application for the scopes "openid"
        And a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        When the user scans the verification link of the device
        And I click "Continue"
        And I click "Deny"
        Then I should see "Authorization denied. You can close this window."
        When the device polls the application
        Then the response status is 400
        And the token error is "access_denied"

    Scenario: A code that was already approved cannot be used again
        Given the device requested a device code from the application for the scopes "openid"
        And a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        And the user scans the verification link of the device
        And I click "Continue"
        And I click "Allow"
        When the user scans the verification link of the device
        And I click "Continue"
        Then I should see "This code has already been used."

    Scenario: A pushed authorization request is redeemed once in the browser
        Given a client application "backend" with the scopes "openid profile email" that skips consent
        And a session is opened for "alice@example.com"
        And the browser holds the cookie of the session
        When the client application "backend" pushes an authorization request for the scopes "openid email"
        And the browser opens the pushed request URI
        Then the callback page of the client application received a code and the state sent
        When the client application redeems the code of the callback page
        Then the response status is 200
        When the browser opens the pushed request URI
        Then the page title should contain "Error"
        And the browser stayed on the authorization server
