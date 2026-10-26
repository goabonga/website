# Domain maintenance

Four periodic Celery tasks keep the fleet of domains healthy without anyone
watching it: they renew certificates before they expire, retire domains whose
DNS no longer points at the platform, retire domains that never became active
and finally purge old soft-deleted rows. They are scheduled by Celery beat and
executed by the worker, like the tasks of the previous features.

## Tasks and schedule

All times are UTC. The beat schedule lives in `custom_domain.celery`; every
entry is published to the queue given by `CELERY_QUEUE`, and the times below are
the defaults of the settings at the end of this page.

| Task | Schedule | What it does |
| --- | --- | --- |
| `check_certificate_expiry` | `CERTIFICATE_EXPIRY_CHECK_CRON` (every day at 02:00) | Selects the `active`, non-deleted domains whose `ssl_expires_at` is earlier than now plus `CERTIFICATE_RENEWAL_DAYS`. For each one it reads the certificate on disk (`certbot_service.check_certificate`) and, when it has `CERTIFICATE_RENEWAL_DAYS` days or fewer left, queues `provision_domain_ssl`, which renews by running the whole provisioning again. |
| `check_domain_health` | at minute `DOMAIN_HEALTH_CHECK_MINUTE` (30) of every `DOMAIN_HEALTH_CHECK_INTERVAL_HOURS` hours (`crontab(hour="*/N")`) | Checks the CNAME of every `active`, non-deleted domain. A valid one has its error message cleared and `last_check_at` updated. |
| `cleanup_stale_domains` | `STALE_CLEANUP_CRON` (every day at 04:00) | Retires the non-deleted domains that are still `pending`, `dns_verifying`, `dns_verified`, `ssl_provisioning` or `failed` and were created more than `DOMAIN_ACTIVATION_TIMEOUT_HOURS` hours ago. |
| `purge_deleted_domains` | `PURGE_DELETED_CRON` (every Sunday at 05:00) | Permanently deletes the rows soft-deleted more than `SOFT_DELETE_PURGE_DAYS` days ago. |

"Retiring" a domain is a soft delete (`deleted_at` and a reason in
`error_message`) followed by a queued `deprovision_domain` task, which removes
the nginx configuration (SSL provisioning page). Unlike a deletion requested
through the API, a retirement does not revoke the certificate
(`revoke_certificate=False`): a transient DNS problem must not destroy it. The same helper (`soft_delete_domain`) serves both
tasks. The reasons are `DNS no longer valid: <detail>` and `Failed to activate
within N hours`.

The health check has no grace period: one failed CNAME check marks the domain
`failed`, soft-deletes it and removes its nginx configuration at once. A DNS
outage on the resolver side therefore retires every active domain checked
during it.

With the default of 24 hours the health check schedule `*/24` fires once a
day, at 00:30.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CERTIFICATE_RENEWAL_DAYS` | `30` | Renew certificates that expire within this many days. |
| `DOMAIN_ACTIVATION_TIMEOUT_HOURS` | `48` | Age after which a domain that is not active is retired. |
| `DOMAIN_HEALTH_CHECK_INTERVAL_HOURS` | `24` | Hour step of the health check schedule. |
| `DOMAIN_HEALTH_CHECK_MINUTE` | `30` | Minute of the hour at which the health check runs. |
| `SOFT_DELETE_PURGE_DAYS` | `30` | Retention of soft-deleted domains. |
| `CERTIFICATE_EXPIRY_CHECK_CRON` | `0 2 * * *` | When the expiry check runs. |
| `STALE_CLEANUP_CRON` | `0 4 * * *` | When stale domains are retired. |
| `PURGE_DELETED_CRON` | `0 5 * * 0` | When old soft-deleted rows are purged. |

The `*_CRON` settings are five-field cron expressions (minute, hour, day of
month, month, day of week); a malformed one stops beat at start-up with a
`ValueError`. The beat process reads these settings when it starts, so changing a
schedule needs a restart of beat. The worker needs the same settings for the day
thresholds.

## How it is tested

- pytest: `test_tasks_maintenance.py` covers each task (selection of the
  domains, the renewal decision, the health check outcomes, the stale and
  purge thresholds and the soft-delete helper), including the case where the
  certificate cannot be read.
- behave: `features/domain_maintenance.feature` runs the tasks in-process on an
  in-memory database with DNS, certbot and the task queue faked: *A certificate
  close to its expiry is renewed*, *A healthy certificate is left alone*, *An
  active domain with valid DNS stays active*, *An active domain whose DNS broke
  is soft-deleted and deprovisioned*, *A domain that never became active is
  retired*, *Old soft-deleted domains are purged* and *The maintenance tasks are
  scheduled* and *The maintenance tasks are published to the worker queue at the
  configured times*. The cron settings are exercised in `test_celery.py`.
