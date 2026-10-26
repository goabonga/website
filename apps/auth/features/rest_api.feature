Feature: REST API v1
    As an operator or an integration
    I want to manage identity resources through a bearer-token JSON API
    So that users, scopes, roles, clients and tokens can be automated

    Background:
        Given an empty user database
        And a verified user "admin@example.com" with the password "Sup3r!secret"

    Scenario: Requests without a token are refused
        When I send a GET request to "/api/v1/users/"
        Then the response status is 401
        And the response JSON field "detail" is "Missing access token"

    Scenario: A token without the required scope is refused
        Given "admin@example.com" holds a personal access token with the scopes "me:read"
        When I GET "/api/v1/users/" with the token
        Then the response status is 403
        And the response JSON field "detail" is "Missing required permission: users:read"

    Scenario: An unknown token is refused
        When I GET "/api/v1/users/" with the bearer value "pat_unknown"
        Then the response status is 401

    Scenario: An administrator manages the lifecycle of a user
        Given "admin@example.com" holds a personal access token with the scopes "users:*"
        When I POST "/api/v1/users/" with the token and the JSON body
            """
            {"email": "alice@example.com", "password": "Alice!pass1"}
            """
        Then the response status is 201
        And the response JSON field "email" is "alice@example.com"
        And the response JSON field "is_active" is "True"
        When I PATCH the created resource with the token and the JSON body
            """
            {"nickname": "ally"}
            """
        Then the response status is 200
        When I GET the created resource with the token
        Then the response JSON field "nickname" is "ally"
        When with the token I POST the sub-path "/disable" of the created resource
        Then the response JSON field "is_active" is "False"
        When with the token I POST the sub-path "/enable" of the created resource
        Then the response JSON field "is_active" is "True"
        When I GET "/api/v1/users/?page_size=1" with the token
        Then the response JSON field "total" is "2"
        And the response JSON field "page_size" is "1"
        When I DELETE the created resource with the token
        Then the response status is 204
        When I GET the created resource with the token
        Then the response status is 404

    Scenario: A duplicate e-mail address is a conflict
        Given "admin@example.com" holds a personal access token with the scopes "users:write"
        When I POST "/api/v1/users/" with the token and the JSON body
            """
            {"email": "admin@example.com", "password": "Alice!pass1"}
            """
        Then the response status is 409

    Scenario: Custom scopes are created and protected against duplicates
        Given "admin@example.com" holds a personal access token with the scopes "scopes:*"
        When I POST "/api/v1/scopes/" with the token and the JSON body
            """
            {"name": "reports:read", "resource": "reports", "action": "read", "category": "reporting"}
            """
        Then the response status is 201
        And the response JSON field "is_system" is "False"
        When I POST "/api/v1/scopes/" with the token and the JSON body
            """
            {"name": "reports:read", "resource": "reports", "action": "read"}
            """
        Then the response status is 409
        When I DELETE the created resource with the token
        Then the response status is 204

    Scenario: A role carries scopes and is assigned to a user
        Given "admin@example.com" holds a personal access token with the scopes "roles:* scopes:*"
        And a custom scope "reports:read" exists
        When I POST "/api/v1/roles/" with the token and the JSON body
            """
            {"name": "analyst", "scope_ids": ["{scope_id}"]}
            """
        Then the response status is 201
        And the response JSON field "name" is "analyst"
        When I assign the created role to "admin@example.com" with the token
        Then the response status is 201
        And the user "admin@example.com" has the role "analyst"

    Scenario: An OAuth2 client is created with its secret shown once
        Given "admin@example.com" holds a personal access token with the scopes "clients:*"
        When I POST "/api/v1/clients/" with the token and the JSON body
            """
            {"name": "Portal", "redirect_uris": ["https://app.example.com/callback"]}
            """
        Then the response status is 201
        And the response JSON field "name" is "Portal"
        And the response contains a client secret
        When I GET the created resource with the token
        Then the response does not contain a client secret
        When with the token I POST the sub-path "/rotate-secret" of the created resource
        Then the response status is 200
        And the response contains a client secret

    Scenario: The current user reads the profile through a token
        Given "admin@example.com" holds a personal access token with the scopes "me:read"
        When I GET "/api/v1/me/" with the token
        Then the response status is 200
        And the response JSON field "nickname" is "None"

    Scenario: Personal access tokens are listed and revoked by their owner
        Given "admin@example.com" holds a personal access token with the scopes "me:read"
        When I POST "/api/v1/me/pats/" with the token and the JSON body
            """
            {"name": "ci", "scopes": ["me:read"], "expiration_preset": "30_days"}
            """
        Then the response status is 201
        And the response contains a new personal access token
        When I GET "/api/v1/me/pats/" with the token
        Then the response JSON field "total" is "2"
        When I DELETE the created resource with the token
        Then the response status is 204

    Scenario: An administrator revokes the sessions of a user
        Given "admin@example.com" holds a personal access token with the scopes "users:write"
        And a session is opened for "admin@example.com"
        When I DELETE "/api/v1/users/{admin_id}/sessions" with the token
        Then the response status is 204
        And the user "admin@example.com" has 0 active sessions
