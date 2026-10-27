@browser
Feature: Application foundation in a browser
    As an operator
    I want the documentation page and the probes of the service to work from a locked-down network
    So that the API can be explored and monitored without reaching the internet

    Scenario: Swagger UI renders the API from local assets only
        Given the browser records the requests it makes
        When I navigate to "/docs"
        Then I should see "OIDC/OAuth2 Service"
        And "css=a[href='/openapi.json']" should be visible
        And every request of the browser went to the application
        And the browser should report no errors

    Scenario: The health probe answers in the browser
        When I navigate to "/health"
        Then I should see "healthy"

    Scenario: The favicon is served as an image
        When I fetch "/static/favicon.ico" with the browser
        Then the browser received an image

    Scenario: An unknown path shows a JSON error
        When I navigate to "/does-not-exist"
        Then I should see "Not Found"
