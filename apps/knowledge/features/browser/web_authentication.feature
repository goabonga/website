@browser
Feature: Web authentication and account pages in a browser
  As a visitor of the web application
  I want to sign up, sign in and manage my account in a browser
  So that I can use my workspace through the identity provider

  Background:
    Given a user "Alice" who holds every knowledge scope

  Scenario: A visitor signs in through the identity provider with PKCE
    When I navigate to "/auth/login?redirect=/auth/account"
    Then I should be at the identity provider
    And the authorization request used the S256 code challenge method
    When I sign in as "Alice" at the identity provider
    Then the URL should be "/auth/account"
    And I should see "Profile Information"
    And the identity provider issued tokens for the "authorization_code" grant
    And the browser should hold the cookie "access_token"
    And the browser should hold the cookie "active_tenant_id"
    And the workspace "Alice's Workspace" should exist on the "free" plan
    And the browser should report no errors

  Scenario: A wrong password at the identity provider is refused
    When I navigate to "/auth/login"
    And I fill "Email" with "alice@example.test"
    And I fill "Password" with "not the password"
    And I click "Sign in"
    Then I should see "Invalid email or password."
    And I should be at the identity provider
    And the browser should not hold the cookie "access_token"

  Scenario: A protected page sends the visitor to sign in and brings them back
    When I navigate to "/auth/account/security"
    Then I should be at the identity provider
    When I sign in as "Alice" at the identity provider
    Then the URL should be "/auth/account/security"
    And I should see "Change Password"

  Scenario: The return address of a protected page keeps its query string
    When I navigate to "/auth/account?success=Saved&view=compact"
    And I sign in as "Alice" at the identity provider
    Then the URL should be "/auth/account?success=Saved&view=compact"
    And I should see "Saved"

  Scenario: Signing out clears the session
    Given I have signed in as "Alice" through the identity provider
    When I navigate to "/auth/account"
    And I click "Logout"
    Then the URL should be "/"
    And the browser should not hold the cookie "access_token"
    And the browser should not hold the cookie "active_tenant_id"

  Scenario: A token revoked at the provider sends the user back to sign in
    Given I have signed in as "Alice" through the identity provider
    When the identity provider revokes every token and ends the sessions
    And I navigate to "/auth/account"
    Then I should be at the identity provider

  Scenario: A visitor signs up, verifies the email and signs in
    When I navigate to "/auth/signup"
    And I click "Continue"
    And I fill "Nickname" with "ada"
    And I fill "First Name" with "Ada"
    And I fill "Last Name" with "Lovelace"
    And I fill "Workspace name" with "Analytical Engines"
    And I fill "Email address" with "ada@example.test"
    And I fill "Password" with "Long-passphrase-1!"
    And I fill "Confirm password" with "Long-passphrase-1!"
    And I click "Create Account"
    Then the URL should contain "/auth/verify"
    And I should see "ada@example.test"
    When I enter the verification code sent to "ada@example.test"
    Then the URL should contain "/auth/signin"
    And I should see "Email verified successfully"
    When I fill "Email address" with "ada@example.test"
    And I fill "Password" with "Long-passphrase-1!"
    And I click "Sign In"
    Then the URL should be "/dashboard"
    And the browser should hold the cookie "active_tenant_id"
    And the workspace "Analytical Engines" should exist on the "free" plan

  Scenario: Signing up requires matching passwords
    Given the browser records the alerts it shows
    When I navigate to "/auth/signup"
    And I click "Continue"
    And I fill "Nickname" with "ada"
    And I fill "First Name" with "Ada"
    And I fill "Last Name" with "Lovelace"
    And I fill "Workspace name" with "Analytical Engines"
    And I fill "Email address" with "ada@example.test"
    And I fill "Password" with "Long-passphrase-1!"
    And I fill "Confirm password" with "Another-passphrase-2!"
    And I click "Create Account"
    Then the browser should have shown the alert "Passwords do not match"
    And the URL should be "/auth/signup"
    And no verification code was sent

  Scenario: Signing up requires a password that meets the rules
    Given the browser records the alerts it shows
    When I navigate to "/auth/signup"
    And I click "Continue"
    And I fill "Nickname" with "ada"
    And I fill "First Name" with "Ada"
    And I fill "Last Name" with "Lovelace"
    And I fill "Workspace name" with "Analytical Engines"
    And I fill "Email address" with "ada@example.test"
    And I fill "Password" with "weakpassword"
    And I fill "Confirm password" with "weakpassword"
    And I click "Create Account"
    Then the browser should have shown the alert "Password does not meet all requirements."
    And no verification code was sent

  Scenario: A wrong verification code is refused
    Given "ada@example.test" has registered and awaits the verification code
    When I navigate to "/auth/verify?email=ada@example.test"
    And I type the verification code "000000"
    Then I should see "Invalid verification code"

  Scenario: The sign-in page refuses a wrong password
    When I navigate to "/auth/signin"
    And I fill "Email address" with "alice@example.test"
    And I fill "Password" with "not the password"
    And I click "Sign In"
    Then I should see "Invalid email or password"
    And the browser should not hold the cookie "access_token"

  Scenario: The sign-in page signs a user with a password in
    When I navigate to "/auth/signin"
    And I fill "Email address" with "alice@example.test"
    And I fill "Password" with the password of the users
    And I click "Sign In"
    Then the URL should be "/auth/create-workspace"
    When I fill "Workspace name" with "Notebook"
    And I click "Create Workspace"
    Then the URL should be "/dashboard"
    And the workspace "Notebook" should exist on the "free" plan

  Scenario: The sign-in page offers the identity provider
    When I navigate to "/auth/signin"
    And I click "Continue with SSO"
    Then I should be at the identity provider

  Scenario: A forgotten password is reset with the link that was sent
    When I navigate to "/auth/forgot-password"
    And I fill "Email address" with "alice@example.test"
    And I click "Send Reset Link"
    Then I should see "If an account exists with this email"
    When I open the password reset link sent to "alice@example.test"
    And I fill "New password" with "Brand-new-passphrase-3!"
    And I fill "Confirm password" with "Brand-new-passphrase-3!"
    And I click "Reset Password"
    Then the URL should contain "/auth/signin"
    And I should see "Password reset successfully"
    When I fill "Email address" with "alice@example.test"
    And I fill "Password" with "Brand-new-passphrase-3!"
    And I click "Sign In"
    Then the URL should be "/auth/create-workspace"

  Scenario: A reset link without a token is refused
    When I navigate to "/auth/reset-password"
    Then I should see "Invalid or missing reset token"

  Scenario: The account pages require a signed-in user
    When I navigate to "/auth/account"
    Then I should be at the identity provider

  Scenario: A signed-in user updates their profile
    Given I have signed in as "Alice" through the identity provider
    When I navigate to "/auth/account/security"
    And I click "Profile"
    Then the URL should be "/auth/account"
    When I fill "Nickname" with "ally"
    And I click "Save Changes"
    Then I should see "Profile updated successfully"
    And the authentication service holds the nickname "ally" for "alice@example.test"

  Scenario: The security page shows the two-factor status
    Given I have signed in as "Alice" through the identity provider
    When I navigate to "/auth/account"
    And I click "Security"
    Then the URL should be "/auth/account/security"
    And I should see "Change Password"

  Scenario: The sidebar of the account pages only leads to pages that exist
    Given I have signed in as "Alice" through the identity provider
    When I navigate to "/auth/account"
    Then the sidebar item "Profile" should be the active one
    And every link of the navigation leads to a page of the application
    When I click "Security"
    Then the sidebar item "Security" should be the active one
    And every link of the navigation leads to a page of the application
