Feature: Nginx template administration
  Administrators manage the nginx templates used to render domain configurations. Every
  endpoint requires both the custom-domain:admin and custom-domain:admin:templates scopes.

  Background:
    Given I am authenticated as client "ops" with scopes "custom-domain:admin custom-domain:admin:templates"

  Scenario: Creating a template
    When I send a POST request to "/api/v1/admin/templates" with JSON
      """
      {
        "slug": "static-site",
        "name": "Static site",
        "http_template": "server { server_name {{ domain }}; }",
        "https_template": "server { listen 443 ssl; server_name {{ domain }}; }"
      }
      """
    Then the response status is 201
    And the JSON field "slug" equals "static-site"
    And the JSON field "is_default" is false
    And the JSON field "is_active" is true

  Scenario: A slug can only be used once
    Given a template "static-site" exists
    When I send a POST request to "/api/v1/admin/templates" with JSON
      """
      {"slug": "static-site", "name": "Again", "http_template": "a", "https_template": "b"}
      """
    Then the response status is 409

  Scenario: A template with a syntax error is refused
    When I send a POST request to "/api/v1/admin/templates" with JSON
      """
      {"slug": "broken", "name": "Broken", "http_template": "{% if %}", "https_template": "b"}
      """
    Then the response status is 400
    And the JSON field "detail" contains "Invalid HTTP template"

  Scenario: Listing templates reports how many domains use each one
    Given a template "static-site" exists
    And a domain "a.example.com" with the status "active" in the database
    And the domain "a.example.com" uses the template "static-site"
    When I send a GET request to "/api/v1/admin/templates"
    Then the response status is 200
    And the JSON field "total" equals "1"
    And the first item has the domain count 1

  Scenario: Choosing a new default template
    Given a template "first" exists
    And the template "first" is the default
    And a template "second" exists
    When I send a POST request to "/api/v1/admin/templates/{template:second}/set-default"
    Then the response status is 200
    And the JSON field "is_default" is true
    And the template "first" is not the default any more

  Scenario: The default template cannot be deleted
    Given a template "first" exists
    And the template "first" is the default
    When I send a DELETE request to "/api/v1/admin/templates/{template:first}"
    Then the response status is 400

  Scenario: A template used by a domain cannot be deleted
    Given a template "static-site" exists
    And a domain "a.example.com" with the status "active" in the database
    And the domain "a.example.com" uses the template "static-site"
    When I send a DELETE request to "/api/v1/admin/templates/{template:static-site}"
    Then the response status is 400

  Scenario: Deleting an unused template
    Given a template "static-site" exists
    When I send a DELETE request to "/api/v1/admin/templates/{template:static-site}"
    Then the response status is 204

  Scenario: Validating a template with test variables
    Given a template "static-site" exists
    And nginx accepts every configuration
    When I send a POST request to "/api/v1/admin/templates/{template:static-site}/validate" with JSON
      """
      {"test_variables": {"domain": "check.example.com"}}
      """
    Then the response status is 200
    And the JSON field "valid" is true
    And the JSON field "rendered_http" contains "server_name check.example.com;"

  Scenario: The nginx check is delegated to a worker
    Given a template "static-site" exists
    And no worker answers the nginx validation
    When I send a POST request to "/api/v1/admin/templates/{template:static-site}/validate" with JSON
      """
      {"test_variables": {"domain": "check.example.com"}}
      """
    Then the response status is 200
    And the JSON field "valid" is false
    And the JSON field "nginx_syntax_valid" is false
    And the JSON field "errors" contains "Nginx validation unavailable"

  Scenario: A dry run counts the domains without queuing anything
    Given a template "static-site" exists
    And a domain "a.example.com" with the status "active" in the database
    And the domain "a.example.com" uses the template "static-site"
    And a domain "b.example.com" with the status "failed" in the database
    And the domain "b.example.com" uses the template "static-site"
    And the provisioning queue is recorded
    When I send a POST request to "/api/v1/admin/templates/{template:static-site}/reprovision" with JSON
      """
      {"only_active": true, "dry_run": true}
      """
    Then the response status is 200
    And the JSON field "domains_affected" equals "1"
    And nothing was queued for provisioning

  Scenario: Reprovisioning queues every active domain of the template
    Given a template "static-site" exists
    And a domain "a.example.com" with the status "active" in the database
    And the domain "a.example.com" uses the template "static-site"
    And the provisioning queue is recorded
    When I send a POST request to "/api/v1/admin/templates/{template:static-site}/reprovision" with JSON
      """
      {"only_active": true, "dry_run": false}
      """
    Then the response status is 200
    And the JSON field "success" equals "1"
    And the domain "a.example.com" was queued for SSL provisioning

  Scenario: The templates scope alone is not enough
    Given I am authenticated as client "ops" with scopes "custom-domain:admin:templates"
    When I send a GET request to "/api/v1/admin/templates"
    Then the response status is 403
