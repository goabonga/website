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

    Scenario: An owner sets, verifies and removes the custom domain
        Given the custom domain tasks are not sent to a broker
        And webhook deliveries are not sent to a broker
        And webhook targets may be private
        And "owner@example.com" owns the organisation "acme"
        When I POST the organisation "acme" sub-path "/webhooks/" with the JSON body
            """
            {"name": "audit", "url": "https://hooks.example.test/events", "events": ["tenant.updated"]}
            """
        Then the response status is 201
        When I GET the organisation "acme" sub-path "/domain/"
        Then the response status is 200
        And the response JSON field "custom_domain" is "None"
        And the response JSON field "status" is "None"
        When I PUT the organisation "acme" sub-path "/domain/" with the JSON body
            """
            {"custom_domain": "Auth.Acme.Example"}
            """
        Then the response status is 200
        And the response JSON field "custom_domain" is "auth.acme.example"
        And the response JSON field "status" is "pending"
        And the organisation "acme" has the custom domain "auth.acme.example"
        And the DNS verification of the custom domain is queued
        And a "tenant.updated" webhook delivery is queued for the organisation "acme"
        When I POST the sub-path "/domain/verify" of the organisation "acme" under "me/organisations"
        Then the response status is 202
        When I DELETE the sub-path "/domain/" of the organisation "acme" under "me/organisations"
        Then the response status is 204
        And the organisation "acme" has no custom domain
        And the removal of the custom domain configuration is queued

    Scenario: The custom domain is also served under the platform prefix
        Given the custom domain tasks are not sent to a broker
        And "owner@example.com" owns the organisation "acme"
        When I PUT the sub-path "/domain/" of the organisation "acme" under "organisations" with the JSON body
            """
            {"custom_domain": "auth.acme.example"}
            """
        Then the response status is 200
        When I GET the sub-path "/domain/" of the organisation "acme" under "organisations"
        Then the response JSON field "custom_domain" is "auth.acme.example"
        When I DELETE the sub-path "/domain/" of the organisation "acme" under "organisations"
        Then the response status is 204

    Scenario: A domain is refused when it is malformed or used by another organisation
        Given the custom domain tasks are not sent to a broker
        And "owner@example.com" owns the organisation "acme"
        And "bob@example.com" owns the organisation "beta"
        And the organisation "beta" has the custom domain "taken.example"
        And "owner@example.com" holds a personal access token with the scopes "me:read"
        When I PUT the organisation "acme" sub-path "/domain/" with the JSON body
            """
            {"custom_domain": "not a domain"}
            """
        Then the response status is 422
        When I PUT the organisation "acme" sub-path "/domain/" with the JSON body
            """
            {"custom_domain": "taken.example"}
            """
        Then the response status is 409
        And the organisation "acme" has no custom domain
        And no custom domain task is queued

    Scenario: The admin role follows the custom domain but cannot change it
        Given the custom domain tasks are not sent to a broker
        And "owner@example.com" owns the organisation "acme"
        And "bob@example.com" is a member of the organisation "acme" with the role "admin"
        And "bob@example.com" holds a personal access token with the scopes "me:read"
        When I GET the organisation "acme" sub-path "/domain/"
        Then the response status is 200
        When I PUT the organisation "acme" sub-path "/domain/" with the JSON body
            """
            {"custom_domain": "auth.acme.example"}
            """
        Then the response status is 403
        And the response JSON field "detail" is "Missing required permission: domain:write"
        When I POST the sub-path "/domain/verify" of the organisation "acme" under "me/organisations"
        Then the response status is 403
        And the organisation "acme" has no custom domain
        And no custom domain task is queued

    Scenario: A member without a domain scope sees nothing of the domain
        Given "owner@example.com" owns the organisation "acme"
        And "bob@example.com" is a member of the organisation "acme" with the role "member"
        And "bob@example.com" holds a personal access token with the scopes "me:read"
        When I GET the organisation "acme" sub-path "/domain/"
        Then the response status is 403
        And the response JSON field "detail" is "Missing required permission: domain:read"
