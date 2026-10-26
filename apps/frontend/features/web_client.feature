Feature: Web client and template generator
  The Vite and TypeScript web client lives next to the server. Its build
  turns the built page into the Jinja2 template that the server renders.

  Scenario: The web client sources are part of the application
    Then the web client contains "package.json"
    And the web client contains "vite.config.ts"
    And the web client contains "src/main.ts"
    And the web client contains "scripts/generate-template.js"

  Scenario: The build script type-checks, bundles and generates the template
    Then the "build" npm script runs "tsc", then "vite build", then "generate-template.js"

  Scenario: The committed template is parametrised by the server settings
    Then the committed template uses the variable "auth_url"
    And the committed template uses the variable "client_id"
    And the committed template uses the variable "legal_company_name"
    And the committed template uses the variable "welcome_words"
    And the committed template contains no personal default value

  Scenario: The generator turns a built page into a template
    Given a built page containing hard-coded values
    When the template generator runs
    Then the generated template contains "<title>{{ app_name }}</title>"
    And the generated template contains "{{ api_url | tojson }}"
    And the generated template no longer contains "ea2457629d5f4680e3968df232849fde"

  Scenario: The generator refuses to run without a build
    Given no built page
    When the template generator runs
    Then the generator fails asking to run the build first
