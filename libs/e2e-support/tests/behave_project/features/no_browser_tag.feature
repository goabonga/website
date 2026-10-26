Feature: Browser steps need the tag

  @fails
  Scenario: A browser step without the tag fails with an explanation
    Given I navigate to "/dashboard"
