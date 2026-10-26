Feature: Multi-tenancy and OIDC discovery
    As a platform operator
    I want every request to be attributed to an organisation (tenant)
    So that each tenant gets its own issuer, branding, cookies and sign-in policy

    Scenario: The platform publishes its OpenID Connect discovery document
        Given the issuer is configured as "https://auth.example.test"
        When I send a GET request to "/.well-known/openid-configuration"
        Then the response status is 200
        And the response JSON field "issuer" is "https://auth.example.test"
        And the response JSON field "token_endpoint" is "https://auth.example.test/oauth2/token"
        And the response JSON field "jwks_uri" is "https://auth.example.test/.well-known/jwks.json"

    Scenario Outline: The issuer follows the tenant
        Given the tenant base domain is "auth.example.test"
        And a <kind> tenant with slug "acme" and custom domain "<domain>"
        When the issuer of the tenant is computed
        Then the issuer is "<issuer>"

        Examples:
            | kind     | domain             | issuer                         |
            | platform | -                  | https://auth.example.test      |
            | regular  | -                  | https://acme.auth.example.test |
            | regular  | login.acme.example | https://login.acme.example     |

    Scenario: A tenant is resolved from its subdomain
        Given the tenant middleware serves the base domain "auth.example.test"
        And the tenant "acme" exists
        When I request "/ping" on the host "acme.auth.example.test"
        Then the request is attributed to the tenant "acme" by "subdomain"

    Scenario: A tenant is resolved from a path prefix
        Given the tenant middleware serves the base domain "auth.example.test"
        And the tenant "acme" exists
        When I request "/t/acme/ping" on the host "auth.example.test"
        Then the request is attributed to the tenant "acme" by "path"
        And the application sees the path "/ping"

    Scenario: A tenant is resolved from its custom domain
        Given the tenant middleware serves the base domain "auth.example.test"
        And the tenant "acme" exists with the custom domain "login.acme.example"
        When I request "/ping" on the host "login.acme.example"
        Then the request is attributed to the tenant "acme" by "custom_domain"

    Scenario: The main domain falls back to the platform tenant
        Given the tenant middleware serves the base domain "auth.example.test"
        And the platform tenant "platform" exists
        When I request "/ping" on the host "auth.example.test"
        Then the request is attributed to the tenant "platform" by "platform"

    Scenario: An unknown subdomain is redirected to the main domain
        Given the tenant middleware serves the base domain "auth.example.test"
        And the platform tenant "platform" exists
        When I request "/ping?x=1" on the host "ghost.auth.example.test"
        Then the client is redirected to "https://auth.example.test/ping?x=1"

    Scenario: Cookie names are scoped to the tenant
        Given the tenant base domain is "auth.example.test"
        When the request context is the tenant "acme" resolved by "subdomain"
        Then the session cookie is named "session_acme"
        And the CSRF cookie is named "csrf_acme"
        And the cookie domain is ".auth.example.test"
        When the request context is the tenant "acme" resolved by "custom_domain"
        Then the session cookie is named "session"
        And the cookie domain is not set

    Scenario: Creating an organisation seeds its roles and enrols the owner
        Given a registered user
        When the user creates the organisation "acme"
        Then the organisation has the roles "owner, admin, member"
        And the user is a member with the role "owner"
        And creating the organisation "acme" again is refused

    Scenario Outline: Trust policies decide who may sign in to a tenant
        Given a tenant with the trust mode "<mode>"
        And a user registered on the <origin> tenant who is <membership>
        When the sign-in is evaluated
        Then the sign-in is <decision>

        Examples:
            | mode         | origin  | membership      | decision |
            | none         | same    | not a member    | allowed  |
            | none         | another | not a member    | denied   |
            | none         | another | a member        | allowed  |
            | members_only | another | not a member    | denied   |
            | members_only | another | a member        | allowed  |
            | all          | another | not a member    | allowed  |
            | specific     | trusted | not a member    | allowed  |
            | specific     | another | not a member    | denied   |

    Scenario: Branding falls back to the platform defaults
        When the branding of a missing tenant is requested
        Then the branding uses the primary color "#e94560"
        And the generated CSS defines "--primary-color: #e94560"
