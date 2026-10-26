Feature: Browser hooks

  @browser
  Scenario: A browser scenario gets a page
    When I open "/hello" with the raw page
    Then the raw page title is "Page /hello"
    And the context holds a page, a browser context and the base URL

  Scenario: A scenario without the tag gets no browser
    Then the context holds no page

  @browser
  Scenario: First scenario sets a cookie
    When I visit the page that sets a cookie

  @browser
  Scenario: The next scenario does not see that cookie
    Then the cookie jar is empty

  @browser @fails
  Scenario: A failing browser scenario keeps its artifacts
    When I open "/console" with the raw page
    Then the scenario fails on purpose
