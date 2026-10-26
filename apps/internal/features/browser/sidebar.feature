@browser
Feature: Admin sidebar across all pages in a browser
  As an operator
  I want the sidebar to list the sections I may use and to highlight the current one
  So that I can move around the dashboard from any page

  # The sidebar is built from the scopes that the application obtains by exchanging the access
  # token at the provider: the token of a login only carries the OpenID scopes, the provider
  # grants the requested scopes the user holds.

  Background:
    Given every service answers with some data

  # --- Links by scope ---

  Scenario: A super administrator sees every section
    Given I sign in as a super administrator
    When I navigate to "/analytics"
    Then the sidebar menu should list exactly these links
      | label           | href             |
      | Dashboard       | /                |
      | Chat History    | /conversations   |
      | Knowledge Base  | /knowledge       |
      | Namespaces      | /namespaces      |
      | Prompts         | /prompts         |
      | Analytics       | /analytics       |
      | Email Templates | /email-templates |
      | Email Campaigns | /email-campaigns |
      | Mailler Stats   | /mailler         |
      | Contacts        | /contacts        |
      | Contact Groups  | /contact-groups  |
      | VPN             | /vpn/sessions    |
      | Billing         | /billing         |
      | Team AI         | /team            |

  Scenario: A user without the VPN and billing scopes does not see them
    Given I sign in with the scopes "analytics:*"
    When I navigate to "/analytics"
    Then the sidebar menu should list exactly these links
      | label           | href             |
      | Dashboard       | /                |
      | Chat History    | /conversations   |
      | Knowledge Base  | /knowledge       |
      | Namespaces      | /namespaces      |
      | Prompts         | /prompts         |
      | Analytics       | /analytics       |
      | Email Templates | /email-templates |
      | Email Campaigns | /email-campaigns |
      | Mailler Stats   | /mailler         |
      | Contacts        | /contacts        |
      | Contact Groups  | /contact-groups  |
      | Team AI         | /team            |

  Scenario Outline: The gated links follow the scopes of the user
    Given I sign in with the scopes "<scopes>"
    When I navigate to "<path>"
    Then the sidebar menu entry "VPN" should be <vpn>
    And the sidebar menu entry "Billing" should be <billing>

    Examples:
      | path          | scopes                             | vpn     | billing |
      | /analytics    | analytics:*                        | hidden  | hidden  |
      | /analytics    | analytics:* vpn:admin              | visible | hidden  |
      | /analytics    | analytics:* billing:read           | hidden  | visible |
      | /analytics    | analytics:* vpn:admin billing:read | visible | visible |
      | /team         | team:* vpn:admin                   | visible | hidden  |
      | /billing      | billing:read                       | hidden  | visible |
      | /vpn/sessions | vpn:admin                          | visible | hidden  |
      | /contacts/new | contacts:write billing:read        | hidden  | visible |

  Scenario: The exchange asks for the scopes of the page and of the sidebar
    Given I sign in with the scopes "analytics:*"
    When I navigate to "/analytics"
    Then the last token exchange should have asked for the scopes "analytics:read vpn:admin billing:read"
    And the last token exchange should have granted only "analytics:read analytics:write analytics:delete"

  Scenario: The exchange grants the sidebar scopes the user holds
    Given I sign in with the scopes "analytics:read vpn:admin"
    When I navigate to "/analytics"
    Then the last token exchange should have granted only "analytics:read vpn:admin"

  # --- Highlighted section on every kind of page ---

  Scenario Outline: The highlighted link follows the page
    Given I sign in as a super administrator
    When I navigate to "<path>"
    Then the sidebar menu should highlight only "<section>"
    And the sidebar menu should show the signed in user

    Examples:
      | path                    | section         |
      | /                       | Dashboard       |
      | /conversations          | Chat History    |
      | /knowledge              | Knowledge Base  |
      | /knowledge/new          | Knowledge Base  |
      | /knowledge/generate     | Knowledge Base  |
      | /namespaces             | Namespaces      |
      | /namespaces/new         | Namespaces      |
      | /prompts                | Prompts         |
      | /prompts/new            | Prompts         |
      | /analytics              | Analytics       |
      | /analytics/campaigns    | Analytics       |
      | /analytics/ips          | Analytics       |
      | /email-templates        | Email Templates |
      | /email-templates/new    | Email Templates |
      | /email-campaigns        | Email Campaigns |
      | /email-campaigns/new    | Email Campaigns |
      | /mailler                | Mailler Stats   |
      | /mailler/emails         | Mailler Stats   |
      | /contacts               | Contacts        |
      | /contacts/new           | Contacts        |
      | /contacts/import        | Contacts        |
      | /contact-groups         | Contact Groups  |
      | /contact-groups/new     | Contact Groups  |
      | /vpn/sessions           | VPN             |
      | /billing                | Billing         |
      | /billing/saas/new       | Billing         |
      | /team                   | Team AI         |
      | /team/new               | Team AI         |

  Scenario: Every link of the sidebar leads to its section
    Given I sign in as a super administrator
    When I navigate to "/analytics"
    And I follow every link of the sidebar in turn
    Then the sidebar links should have led to these pages
      | label           | path             |
      | Dashboard       | /                |
      | Chat History    | /conversations   |
      | Knowledge Base  | /knowledge       |
      | Namespaces      | /namespaces      |
      | Prompts         | /prompts         |
      | Analytics       | /analytics       |
      | Email Templates | /email-templates |
      | Email Campaigns | /email-campaigns |
      | Mailler Stats   | /mailler         |
      | Contacts        | /contacts        |
      | Contact Groups  | /contact-groups  |
      | VPN             | /vpn/sessions    |
      | Billing         | /billing         |
      | Team AI         | /team            |

  # --- Pages that are refused ---

  Scenario: A user holding only the scopes of the sidebar is refused the pages of the sections
    Given I sign in with the scopes "vpn:admin billing:read"
    When I navigate to "/contacts"
    Then the page title should contain "Access Denied"
    And I should see "contacts:read"
    And the last token exchange should have granted only "vpn:admin billing:read"
    And the sidebar menu should not be shown

  Scenario Outline: A user without the scope of a section is refused its pages
    Given I sign in with the scopes "contacts:*"
    When I navigate to "<path>"
    Then the page title should contain "Access Denied"
    And I should see "<scope>"
    And the sidebar menu should not be shown

    Examples:
      | path             | scope            |
      | /conversations   | conversations:read |
      | /knowledge       | knowledge:read   |
      | /namespaces      | namespaces:read  |
      | /prompts         | prompts:read     |
      | /analytics       | analytics:read   |
      | /email-templates | email_templates:read |
      | /email-campaigns | email_campaigns:read |
      | /mailler         | mailler:read     |
      | /vpn/sessions    | vpn:admin        |
      | /billing         | billing:read     |
      | /team            | team:read        |

  Scenario: A user holding no scope at all is refused
    Given I sign in with no scope
    When I navigate to "/"
    Then the page title should contain "Access Denied"
    And the sidebar menu should not be shown

  # --- Sign out and narrow screens ---

  Scenario: The user is shown in the sidebar and signs out from it
    Given I sign in with the scopes "analytics:*"
    And the provider ends every session
    When I navigate to "/analytics"
    Then the sidebar menu should show the signed in user
    When I sign out from the sidebar
    Then the cookie "access_token" should not be set
    And I should be asked to sign in at the provider

  Scenario: On a narrow screen the sidebar is a menu that opens
    Given a narrow screen
    And I sign in with the scopes "analytics:*"
    When I navigate to "/analytics"
    Then the sidebar menu should be off screen
    When I open the menu
    Then the sidebar menu should be on screen
    And the sidebar menu should have a link "Analytics" to "/analytics"
