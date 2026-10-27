Feature: Catalog of scopes and roles
    As an operator
    I want the scopes and roles of the services of my platform declared in one file
    So that every deployment creates them with a single idempotent command, not with migrations

    Background:
        Given an empty user database
        And a catalog file:
            """
            {
              "scopes": [
                {"name": "notes:read", "description": "Read notes"},
                {"name": "notes:write", "description": "Write notes", "category": "app"}
              ],
              "roles": [
                {"name": "notes_editor", "description": "Edit notes", "scopes": ["notes:read", "notes:write"]}
              ]
            }
            """

    Scenario: The first synchronisation creates the scopes and the roles
        When I run "auth catalog sync" with the catalog file
        Then the command exits with 0
        And the command prints "created scope notes:read"
        And the command prints "created role notes_editor with 2 scope(s)"
        And the scope "notes:read" exists in the category "api" with the description "Read notes"
        And the scope "notes:write" exists in the category "app" with the description "Write notes"
        And the role "notes_editor" holds the scopes "notes:read, notes:write"

    Scenario: Running it again changes nothing
        Given the catalog was synchronised
        When I run "auth catalog sync --json" with the catalog file
        Then the command exits with 0
        And the JSON report says nothing changed

    Scenario: A dry run reports the changes and applies none
        When I run "auth catalog sync --dry-run" with the catalog file
        Then the command exits with 0
        And the command prints "would create scope notes:read"
        And no scope "notes:read" exists

    Scenario: Descriptions are updated and scopes are added to existing roles, nothing is removed
        Given the catalog was synchronised
        And the catalog file is replaced by:
            """
            {
              "scopes": [
                {"name": "notes:read", "description": "Read all notes"},
                {"name": "notes:share"}
              ],
              "roles": [{"name": "notes_editor", "scopes": ["notes:share"]}]
            }
            """
        When I run "auth catalog sync" with the catalog file
        Then the command exits with 0
        And the command prints "updated scope notes:read (description)"
        And the command prints "updated role notes_editor (+notes:share)"
        And the scope "notes:read" exists in the category "api" with the description "Read all notes"
        And the role "notes_editor" holds the scopes "notes:read, notes:write, notes:share"

    Scenario: The listed allowances are added to an existing client only
        Given an OAuth2 client "kb-client" allowed the scopes "openid" and the grant types "authorization_code"
        And the catalog file is replaced by:
            """
            {
              "clients": [
                {"client_id": "kb-client", "allowed_scopes": ["notes:read"], "allowed_grant_types": ["client_credentials"]},
                {"client_id": "absent-client", "allowed_scopes": ["notes:read"]}
              ],
              "scopes": [{"name": "notes:read"}]
            }
            """
        When I run "auth catalog sync" with the catalog file
        Then the command exits with 0
        And the command prints "updated client kb-client (+notes:read, +client_credentials)"
        And the command prints "skipped client absent-client (not found)"
        And the client "kb-client" is allowed the scopes "openid, notes:read"
        And the client "kb-client" is allowed the grant types "authorization_code, client_credentials"
        And no OAuth2 client "absent-client" exists

    Scenario: A role may only hold known scopes
        Given the catalog file is replaced by:
            """
            {"roles": [{"name": "broken", "scopes": ["ghost:read"]}]}
            """
        When I run "auth catalog sync" with the catalog file
        Then the command exits with 2
        And the command reports the error "unknown scopes: ghost:read"
        And no role "broken" exists

    Scenario: A malformed catalog is refused
        Given the catalog file is replaced by:
            """
            {"scopes": [{"name": "has space"}]}
            """
        When I run "auth catalog sync" with the catalog file
        Then the command exits with 2
        And the command reports the error "invalid catalog"

    Scenario: The catalog file comes from the CATALOG_FILE setting
        Given the CATALOG_FILE setting points to the catalog file
        When I run "auth catalog sync"
        Then the command exits with 0
        And the scope "notes:read" exists in the category "api" with the description "Read notes"

    Scenario: Without a file the command explains what is missing
        When I run "auth catalog sync"
        Then the command exits with 2
        And the command reports the error "no catalog file"
