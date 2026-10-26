Feature: Maintenance tasks and operations scripts
    As an operator
    I want expired data purged and common administration done from the command line
    So that the service stays small and can be bootstrapped without the API

    Background:
        Given an empty user database

    Scenario: Expired and revoked sessions are purged
        Given a verified user "alice@example.com" with the password "Sup3r!secret"
        And a session is opened for "alice@example.com"
        And a second session is opened for "alice@example.com"
        And the session expired one minute ago
        When the task "cleanup_expired_sessions" runs
        Then the task reports "sessions_deleted" as 1
        And the user "alice@example.com" has 1 stored session

    Scenario: Accounts that never verified their address are purged
        Given a verified user "kept@example.com" with the password "Sup3r!secret"
        And an unverified user "stale@example.com" created 30 days ago
        And an unverified user "fresh@example.com" created 1 day ago
        And unverified accounts expire after 7 days
        When the task "cleanup_unverified_users" runs
        Then the task reports "users_deleted" as 1
        And no account exists for "stale@example.com"
        And the account "fresh@example.com" exists and is not verified yet
        And the account "kept@example.com" is still registered

    Scenario: The pairwise backfill needs a platform tenant
        When the task "backfill_pairwise_subjects" runs
        Then the task reports "error" as "no_platform_tenant"

    Scenario: The pairwise backfill has nothing to do without tokens
        Given the platform tenant "platform" exists
        When the task "backfill_pairwise_subjects" runs
        Then the task reports "total" as 0

    Scenario: The beat scheduler knows every maintenance job
        Then the beat schedule contains the jobs
            | job                              |
            | cleanup-expired-tokens           |
            | cleanup-expired-sessions         |
            | cleanup-expired-pats             |
            | cleanup-orphaned-avatars         |
            | cleanup-unverified-users         |
            | check-pending-custom-domains     |

    Scenario Outline: Custom domain names are validated
        Then the custom domain "<domain>" is <verdict>

        Examples:
            | domain               | verdict |
            | shop.example.com     | valid   |
            | -broken.example.com  | invalid |
            | not a domain         | invalid |

    Scenario: A custom domain pointing to the right target is verified
        Given the custom domain target is "edge.example.test"
        And the DNS of "shop.example.com" points to the target
        When the DNS verification of "shop.example.com" runs
        Then the custom domain status becomes "dns_verified"
        And the SSL provisioning is queued for "shop.example.com"

    Scenario: A malformed custom domain is rejected
        Given the custom domain target is "edge.example.test"
        When the DNS verification of "not a domain" runs
        Then the custom domain status becomes "failed"
        And the SSL provisioning is not queued

    Scenario: A missing CNAME target fails the verification
        Given the custom domain target is not configured
        When the DNS verification of "shop.example.com" runs
        Then the custom domain status becomes "failed"

    Scenario: The create_user script bootstraps an account
        When I run the script "create_user.py" with the arguments "--email Boss@Example.com --password Sup3r!secret1 --verified --nickname boss --json"
        Then the script succeeds
        And the script output JSON field "email" is "boss@example.com"
        And the account "boss@example.com" exists and is verified
        And the stored nickname of "boss@example.com" is "boss"

    Scenario: The create_user script refuses an existing address
        Given a verified user "alice@example.com" with the password "Sup3r!secret"
        When I run the script "create_user.py" with the arguments "--email alice@example.com --password Sup3r!secret1"
        Then the script exits with the code 1
        And the script error contains "already exists"

    Scenario: The promote_user script refuses an unknown user
        When I run the script "promote_user.py" with the arguments "--email nobody@example.com --show"
        Then the script exits with the code 1
