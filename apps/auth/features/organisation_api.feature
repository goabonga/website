Feature: Organisation API
    As an organisation owner or a platform administrator
    I want to manage organisations through the JSON API
    So that membership, roles, branding and webhooks can be automated

    Background:
        Given an empty user database
        And a verified user "owner@example.com" with the password "Sup3r!secret"
        And a verified user "bob@example.com" with the password "Sup3r!secret"

    Scenario: A platform administrator needs an organisation scope
        Given "owner@example.com" holds a personal access token with the scopes "me:read"
        When I GET "/api/v1/organisations/" with the token
        Then the response status is 403

    Scenario: A platform administrator manages an organisation
        Given "owner@example.com" holds a personal access token with the scopes "org:*"
        When I POST "/api/v1/organisations/" with the token and the JSON body
            """
            {"slug": "acme", "display_name": "Acme"}
            """
        Then the response status is 201
        And the response JSON field "slug" is "acme"
        And the response JSON field "is_active" is "True"
        And the organisation "acme" includes the roles "owner, member"
        When I POST "/api/v1/organisations/" with the token and the JSON body
            """
            {"slug": "acme", "display_name": "Acme again"}
            """
        Then the response status is 409
        When with the token I POST the sub-path "/disable" of the created resource
        Then the response JSON field "is_active" is "False"
        When with the token I POST the sub-path "/enable" of the created resource
        Then the response JSON field "is_active" is "True"
        When I DELETE the created resource with the token
        Then the response status is 204

    Scenario: A user creates an organisation and becomes its owner
        Given "owner@example.com" holds a personal access token with the scopes "me:read"
        When I POST "/api/v1/me/organisations/" with the token and the JSON body
            """
            {"slug": "acme", "display_name": "Acme"}
            """
        Then the response status is 201
        And "owner@example.com" is a member of the organisation "acme" with the role "owner"
        When I GET "/api/v1/me/organisations/" with the token
        Then the response status is 200
        And the response lists the organisation "acme"

    Scenario: An owner invites and removes a member
        Given "owner@example.com" owns the organisation "acme"
        When I GET the members of the organisation "acme"
        Then the organisation has 1 member
        When I add "bob@example.com" to the organisation "acme" with the role "member"
        Then the response status is 201
        And "bob@example.com" is a member of the organisation "acme" with the role "member"
        When I remove "bob@example.com" from the organisation "acme"
        Then the response status is 204
        And "bob@example.com" is not a member of the organisation "acme"

    Scenario: A member without the permission cannot invite
        Given "owner@example.com" owns the organisation "acme"
        And "bob@example.com" is a member of the organisation "acme" with the role "member"
        And "bob@example.com" holds a personal access token with the scopes "me:read"
        When I add "owner@example.com" to the organisation "acme" with the role "member"
        Then the response status is 403

    Scenario: A stranger cannot read an organisation
        Given "owner@example.com" owns the organisation "acme"
        And "bob@example.com" holds a personal access token with the scopes "me:read"
        When I GET the members of the organisation "acme"
        Then the response status is 403
        And the response JSON field "detail" is "You are not a member of this organisation"

    Scenario: An owner defines a custom role
        Given "owner@example.com" owns the organisation "acme"
        When I POST the organisation "acme" sub-path "/roles/" with the JSON body
            """
            {"name": "auditor", "display_name": "Auditor", "scopes": ["members:read"]}
            """
        Then the response status is 201
        And the response JSON field "name" is "auditor"
        When I GET the organisation "acme" sub-path "/roles/"
        Then the response lists the role "auditor"

    Scenario: An owner customises the branding
        Given "owner@example.com" owns the organisation "acme"
        When I PUT the organisation "acme" sub-path "/branding/" with the JSON body
            """
            {"primary_color": "#112233"}
            """
        Then the response status is 200
        When I GET the organisation "acme" sub-path "/branding/"
        Then the response JSON field "primary_color" is "#112233"

    Scenario: An owner registers a webhook
        Given "owner@example.com" owns the organisation "acme"
        And webhook targets may be private
        When I POST the organisation "acme" sub-path "/webhooks/" with the JSON body
            """
            {"name": "audit", "url": "https://hooks.example.test/events", "events": ["user.created"]}
            """
        Then the response status is 201
        And the response JSON path "webhook.name" is "audit"
        And the response JSON path "webhook.is_active" is "True"
        And the response contains a webhook secret
        When I GET the organisation "acme" sub-path "/webhooks/events"
        Then the response status is 200
        And the response JSON field "groups" lists the event "user.created"
