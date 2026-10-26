Feature: Admin sidebar
  As an admin user
  I want the sidebar to list the sections I may use and to highlight the current one
  So that I can move around the dashboard from any page

  # --- Links by scope ---

  Scenario: A super administrator sees every section
    Given I am authenticated with only the scopes "*" granted by token exchange
    When I send a GET request to "/namespaces"
    Then the response status code should be 200
    And the sidebar should list exactly these links
      | href            |
      | /               |
      | /conversations  |
      | /knowledge      |
      | /namespaces     |
      | /prompts        |
      | /analytics      |
      | /email-templates |
      | /email-campaigns |
      | /mailler        |
      | /contacts       |
      | /contact-groups |
      | /vpn/sessions   |
      | /billing        |
      | /team           |

  Scenario: A user without the VPN and billing scopes does not see them
    Given I am authenticated with only the scopes "namespaces:*" granted by token exchange
    When I send a GET request to "/namespaces"
    Then the response status code should be 200
    And the sidebar should list exactly these links
      | href            |
      | /               |
      | /conversations  |
      | /knowledge      |
      | /namespaces     |
      | /prompts        |
      | /analytics      |
      | /email-templates |
      | /email-campaigns |
      | /mailler        |
      | /contacts       |
      | /contact-groups |
      | /team           |

  Scenario Outline: Gated links follow the scopes
    Given I am authenticated with only the scopes "<scopes>" granted by token exchange
    When I send a GET request to "/namespaces"
    Then the response status code should be 200
    And the sidebar link to "/vpn/sessions" should be <vpn>
    And the sidebar link to "/billing" should be <billing>

    Examples:
      | scopes                              | vpn     | billing |
      | namespaces:*                        | hidden  | hidden  |
      | namespaces:* vpn:admin              | visible | hidden  |
      | namespaces:* billing:read           | hidden  | visible |
      | namespaces:* vpn:admin billing:read | visible | visible |
      | *                                   | visible | visible |

  # --- Active link ---

  Scenario Outline: The active link follows the page
    Given I am authenticated with only the scopes "*" granted by token exchange
    When I send a GET request to "<path>"
    Then the response status code should be 200
    And the active sidebar link should be "<section>"
    And the sidebar should show the user "admin@test.local"

    Examples:
      | path                | section          |
      | /                   | /                |
      | /conversations      | /conversations   |
      | /namespaces         | /namespaces      |
      | /namespaces/new     | /namespaces      |
      | /prompts            | /prompts         |
      | /prompts/new        | /prompts         |
      | /knowledge          | /knowledge       |
      | /knowledge/new      | /knowledge       |
      | /billing/saas/new   | /billing         |
      | /team/new           | /team            |
      | /email-templates/new | /email-templates |
      | /contact-groups/new | /contact-groups  |
      | /contacts/import    | /contacts        |
