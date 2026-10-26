Feature: Application foundation
    As an operator
    I want a service that starts with sensible defaults and reports that it is alive
    So that I can deploy it behind a load balancer and configure it from the environment

    Scenario: The health probe reports a live process
        When I send a GET request to "/health"
        Then the response status is 200
        And the response JSON field "status" is "healthy"
        And the database was not queried

    Scenario: Swagger UI is served from local assets
        When I send a GET request to "/docs"
        Then the response status is 200
        And the response body contains "/static/swagger-ui-bundle.js"
        When I send a GET request to "/static/swagger-ui.css"
        Then the response status is 200

    Scenario: Unknown paths return a JSON error
        When I send a GET request to "/does-not-exist"
        Then the response status is 404
        And the response JSON field "detail" is "Not Found"

    Scenario: Settings fall back to their defaults
        Given no auth variable is set in the environment
        When the settings are loaded
        Then the log level is "INFO"
        And the database URL is "postgresql://localhost:5432/auth"
        And the application title is "OIDC/OAuth2 Service"
        And the Swagger UI client is "swagger-ui" with the scopes "openid profile email"

    Scenario: Settings are overridden by the environment
        Given the environment variable "LOG_LEVEL" is "DEBUG"
        And the environment variable "DATABASE_POOL_SIZE" is "11"
        When the settings are loaded
        Then the log level is "DEBUG"
        And the database pool size is 11

    Scenario: The title and the Swagger UI client come from the environment
        Given the environment variable "APP_TITLE" is "Example Auth"
        And the environment variable "SWAGGER_CLIENT_ID" is "docs-client"
        And the environment variable "SWAGGER_SCOPES" is "openid *"
        When the settings are loaded
        Then the application title is "Example Auth"
        And the Swagger UI client is "docs-client" with the scopes "openid *"

    Scenario: The database URL is converted for the asyncpg driver
        When the async database URL is derived from "postgresql://user@db.example/auth"
        Then the async database URL is "postgresql+asyncpg://user@db.example/auth"
