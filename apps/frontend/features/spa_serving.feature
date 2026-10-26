Feature: Single page application serving
  The server renders the generated template for every path it does not handle,
  fills it with the runtime configuration and serves the client build under
  /static.

  Scenario: Every unknown path serves the application page
    When I request "/some/deep/route"
    Then the response status is 200
    And the response body contains "<title>GOABONGA</title>"

  Scenario: Runtime settings are injected in the page
    Given the setting "app_name" is "TESTAPP"
    And the setting "auth_url" is "https://auth.test"
    And the setting "oauth2_client_id" is "client-123"
    And the setting "welcome_name" is "Alice"
    When I request "/"
    Then the response body contains "<title>TESTAPP</title>"
    And the response body contains "https://auth.test"
    And the response body contains "client-123"
    And the response body contains "Alice"

  Scenario: Welcome words come from the settings
    Given the setting "welcome_words" is "alpha,beta"
    When I request "/"
    Then the response body contains "<b>beta</b>"

  Scenario: Settings values are escaped in the page
    Given the setting "app_name" is "<script>x</script>"
    When I request "/"
    Then the response body does not contain "<title><script>"

  Scenario: Client build files are served under /static
    Given a client build containing "assets/index.js"
    When I request "/static/assets/index.js"
    Then the response status is 200

  Scenario: Missing static files are reported as not found
    Given a client build containing "assets/index.js"
    When I request "/static/assets/other.js"
    Then the response status is 404

  Scenario: Without a client build the page is still served
    Given the setting "static_dir" is "/nonexistent/build"
    When I request "/static/assets/index.js"
    Then the response status is 200
    And the response body contains "<title>GOABONGA</title>"

  Scenario: The health check is not shadowed by the application page
    When I request "/health"
    Then the response JSON field "status" is "healthy"
