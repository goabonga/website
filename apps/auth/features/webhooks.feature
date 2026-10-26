Feature: Outbound webhooks and Celery
    As a tenant administrator
    I want the platform to notify my endpoints when events happen
    So that I can react to them, with signed, retried and safe deliveries

    Scenario: Subscriptions match exact events and wildcards
        When the matching subscription patterns of "mfa.challenge.failed" are computed
        Then the patterns are "mfa.challenge.failed, *, mfa.*, mfa.challenge.*"

    Scenario: Deliveries are signed with a timestamped HMAC
        Given the webhook secret "s3cr3t"
        When the body '{"event":"user.created"}' is signed at the timestamp 1700000000
        Then the signature has the form "t=1700000000,v1=<64 hex digits>"
        And the signature is the HMAC-SHA256 of "1700000000.<body>"
        And signing the same body at the timestamp 1700000001 gives another signature

    Scenario Outline: Unsafe target URLs are rejected
        Given private networks are not allowed
        When the target URL "<url>" is validated
        Then the URL is rejected

        Examples:
            | url                        |
            | ftp://example.test/hook    |
            | http://127.0.0.1:8080/hook |
            | http://10.0.0.5/hook       |
            | http://169.254.169.254/    |

    Scenario: A public target URL is accepted
        Given private networks are not allowed
        When the target URL "https://93.184.216.34/hook" is validated
        Then the URL is accepted

    Scenario: An event creates a delivery for each subscribed endpoint
        Given private networks are allowed
        And the tenant "acme" has a webhook subscribed to "user.*" and another subscribed to "login.*"
        When the event "user.created" is dispatched
        Then 1 delivery is created
        And the delivery is pending with the event "user.created"
        And the delivery task is queued for it

    Scenario: An unsafe endpoint receives no delivery
        Given private networks are not allowed
        And the tenant "acme" has a webhook subscribed to "user.*" and another subscribed to "login.*"
        When the event "user.created" is dispatched
        Then 0 deliveries are created

    Scenario: A successful delivery is recorded
        Given private networks are allowed
        And a pending delivery whose endpoint answers 204
        When the delivery task runs
        Then the delivery status is "success"
        And the request carried a valid signature header
        And the webhook failure count is 0

    Scenario: A failing endpoint is retried with a backoff
        Given private networks are allowed
        And a pending delivery whose endpoint answers 500
        When the delivery task runs
        Then the delivery status is "retrying"
        And the next attempt is scheduled in 60 seconds

    Scenario: The last failed attempt marks the delivery as failed
        Given private networks are allowed
        And a pending delivery whose endpoint answers 500 and allows 1 attempt
        When the delivery task runs
        Then the delivery status is "failed"

    Scenario: The Celery application is configured for the auth queue
        Then the Celery application uses the default queue "auth"
        And the task "deliver_webhook" is registered
        And the beat schedule runs "retry_pending_webhooks" every minute
