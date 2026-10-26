# Policy caching

Sending servers cache a fetched policy for the lifetime announced in it.
This feature makes the HTTP response carry the same lifetime, so that
intermediaries and clients honour it too.

## What it does

The policy endpoint adds a `Cache-Control` header to every response:

```
Cache-Control: max-age=<MTA_STS_MAX_AGE>
```

The value is the same number of seconds as the `max_age` line of the policy
body, so the two never diverge. With the default settings the header is
`Cache-Control: max-age=86400`.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `MTA_STS_MAX_AGE` | `86400` | Policy lifetime in seconds; used for both the `max_age` policy line and the `Cache-Control` header |

The setting itself is introduced by the [policy feature](03-policy.md).

## Operational note

After changing the policy, remote servers may keep serving the previous one
for up to `MTA_STS_MAX_AGE` seconds, and the `id` of the `_mta-sts` DNS TXT
record must be changed so that they refetch it. Lower the value before
planned changes.

## How it is tested

Pytest (`apps/mta-sts/tests/test_mta_sts.py`, class `TestPolicyCaching`):

- the handler sets `Cache-Control: max-age=<value>` from the settings,
- the HTTP response header matches the configured max age.

Behave (`apps/mta-sts/features/caching.feature`), in-process:

- Response has a cache-control header
- Cache lifetime follows the configured max age
