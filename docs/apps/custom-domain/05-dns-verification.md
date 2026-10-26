# DNS verification

Before a certificate can be requested, the customer must create a CNAME record
that points the custom domain at the platform. This feature checks that record
and moves the domain from `pending` to `dns_verified`; success hands the domain
over to the SSL provisioning task of the previous feature.

## DNS service

`custom_domain.services.dns.dns_service` wraps `dnspython` (timeout and lifetime
of `DNS_TIMEOUT_SECONDS`):

- `check_cname(domain, expected_target)` succeeds when one of the domain's
  CNAME records equals the expected target (compared case-insensitively and
  without the trailing dot). Otherwise it returns a failed `DNSCheckResult`
  whose `error_message` is one of `CNAME points to <actual>, expected
  <expected>`, `Domain does not exist (NXDOMAIN)`, `No CNAME record found`,
  `DNS query timed out` or the text of any other error.
- `check_a_record(domain, expected_ip)` does the same for an A record.
- Without `dnspython` the service falls back to the standard library, which
  cannot read CNAME records and therefore always fails the check; the package
  depends on `dnspython`, so the fallback is only a safety net.

## Tasks

### `verify_domain_dns(domain_id)`

1. Ignores unknown or soft-deleted domains.
2. Publishes `step_started` (`dns_check`), sets the status `dns_verifying` and
   stores `last_check_at`.
3. Checks the CNAME against the domain's `cname_target`.
4. On success: status `dns_verified`, `dns_verified_at` set, `error_message`
   cleared, `step_completed` and `status_change` events published, then
   `provision_domain_ssl` is queued.
5. On failure: `error_message` stores the reason, `retry_count` is incremented
   and a `step_failed` event is published. The task is retried with an
   exponential back-off that starts at `DNS_VERIFICATION_RETRY_DELAY_SECONDS` and
   doubles each time, up to `DNS_VERIFICATION_MAX_RETRIES` retries. When the
   retries are exhausted the status becomes `failed` and an `error` event with the code
   `DNS_VERIFICATION_FAILED` (expected and actual values in `details`) is
   published.

Events use the format described in the SSL provisioning page and are published
with the same `publish_event` function.

### `check_pending_domains()`

The periodic task. It selects the domains in `pending` or `dns_verifying`
state that are not deleted, skips the ones checked less than
`DNS_CHECK_INTERVAL_MINUTES` ago and queues `verify_domain_dns` for the others.

The Celery beat schedule `check-pending-domains` runs it every
`DNS_CHECK_INTERVAL_MINUTES` minutes (`crontab(minute="*/N")`). The entry is published to the queue given by
`CELERY_QUEUE`, like every task. Run the
scheduler with:

```bash
uv run --package custom-domain celery -A custom_domain.celery:celery_app beat --loglevel=info
```

Only one beat process should run at a time.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `DNS_CHECK_INTERVAL_MINUTES` | `5` | Period of `check_pending_domains` and minimum delay between two checks of the same domain. |
| `DNS_TIMEOUT_SECONDS` | `10` | Timeout and lifetime of a DNS query. |
| `DNS_VERIFICATION_MAX_RETRIES` | `3` | Retries of `verify_domain_dns`. |
| `DNS_VERIFICATION_RETRY_DELAY_SECONDS` | `300` | Delay before the first retry; it doubles each time. |

## How it is tested

- pytest: `test_services_dns.py` (CNAME and A record checks, every error
  message, the socket fallback), `test_tasks_verification.py` (success,
  failure and error message, retry exhaustion and back-off from the settings,
  selection of the domains by `check_pending_domains` including the recently
  checked and never checked cases), `test_celery.py` (beat entries on the
  configured queue) and the settings assertion in `test_config.py`.
- behave: `features/dns_verification.feature` with *A matching CNAME record is
  accepted*, *A CNAME record pointing elsewhere is rejected*, *A missing domain
  is reported*, *Successful verification triggers SSL provisioning*, *A failed
  verification is retried and counted*, *Verification gives up when the retries
  are exhausted*, *The periodic check only queues domains that are due* and *The
  periodic check is scheduled* and *The periodic scan is published to the queue
  the worker consumes*. The resolver, the database and the task queue
  are faked in-process.
