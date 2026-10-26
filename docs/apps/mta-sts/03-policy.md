# MTA-STS policy

This feature turns the service into an MTA-STS policy server (RFC 8461).
Receiving mail domains publish a policy at
`https://mta-sts.<domain>/.well-known/mta-sts.txt`; sending servers fetch it
to decide whether TLS must be enforced when delivering mail.

## What it does

The policy is stateless and rendered on every request from the settings by
`mta_sts.mta_sts.render_mta_sts_policy()`, one `key: value` pair per line, in
this order:

1. `version: STSv1`
2. `mode: <MTA_STS_MODE>`
3. one `mx: <host>` line per configured MX host
4. `max_age: <MTA_STS_MAX_AGE>`

With the defaults the policy is:

```
version: STSv1
mode: enforce
mx: mail.goabonga.com
max_age: 86400
```

The mode is not validated by the code; the RFC defines `enforce`, `testing`
and `none`. MX hosts are read from a comma-separated list, whitespace and
empty entries are ignored.

## Endpoint

| Endpoint | Description |
| --- | --- |
| `GET /.well-known/mta-sts.txt` | The policy, served as `text/plain` |

The route is registered by `mta_sts.main` through the router of
`mta_sts.mta_sts` and is excluded from the OpenAPI schema.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `MTA_STS_MODE` | `enforce` | Policy mode: `enforce`, `testing` or `none` |
| `MTA_STS_MX` | `mail.goabonga.com` | Authorized MX hosts, comma-separated |
| `MTA_STS_MAX_AGE` | `86400` | Policy lifetime in seconds |

## DNS prerequisites

The service does not manage DNS. Two records are needed for a domain
(placeholders shown):

```
mta-sts.example.com.    IN A/CNAME  <server>
_mta-sts.example.com.   IN TXT  "v=STSv1; id=<timestamp>"
_smtp._tls.example.com. IN TXT  "v=TLSRPTv1; rua=mailto:tlsrpt@example.com"
```

Change the `id` of the `_mta-sts` record whenever the policy changes.

## How it is tested

Pytest (`apps/mta-sts/tests/`):

- `test_config.py` - defaults and overrides of the MTA-STS settings and the
  parsing of `mx_hosts` (single, multiple, whitespace, empty entries).
- `test_mta_sts.py` - policy rendering for each mode, several MX hosts and
  line order, the endpoint response and its HTTP behaviour.

Behave (`apps/mta-sts/features/policy.feature`), in-process:

- Serve the policy at the well-known URL
- Default policy content
- Policy has a key-value structure
- Testing mode is served when configured
- One mx line per configured host
- Configured max age is rendered

Scenarios override settings on the shared `settings` object and restore them
after each scenario.
