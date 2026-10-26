# Workspace custom domain settings

This is the browser side of [Custom domains](13-custom-domains.md): the page on
which an administrator of an Enterprise workspace attaches, follows and removes
the domain. The pages talk to the custom-domain service through its client; the
DNS check, the certificate and the web server configuration are the service's work,
and the status comes back through its webhooks. The routes belong to
`knowledge.routes.web.organizations` (mounted under `/organizations`), render
`tenants/domain.html` and complete the workspace administration pages.

## Access

Every route requires a signed-in user with an active workspace. The page and
the update need the owner or admin role (regular members get the `403` page),
and the workspace must be on the Enterprise plan (`can_use_custom_domain`); any
other plan is redirected to `/organizations/settings`.

## Routes

| Route | Behavior |
| --- | --- |
| `GET /organizations/domain` | The domain page: the current domain and status, the CNAME target the customer must point to (the one the service returned for the workspace, else `CUSTOM_DOMAIN_CNAME_TARGET`), and the instructions. |
| `POST /organizations/domain` | Sets the domain (lowercased and trimmed). It is validated with `validate_domain` and refused when another organization already uses it. Then the previous domain of the workspace, if any, is deleted from the service and the new one is registered (`owner_id` = the workspace id); the workspace gets the service id and the CNAME target, the status `pending` and cleared verification fields. A refusal of the service is shown on the page (`409`: already registered; `403`/`400`: the reason, for example the domain quota; anything else: the service is not available). |
| `POST /organizations/domain/verify` | Asks the service to verify the DNS again (for example after the customer fixed the CNAME). A domain that the service never knew (configured before the service was used) is registered instead. |
| `GET /organizations/domain/status` | JSON for polling: `{"has_domain": false}` or `{"has_domain": true, "domain", "status", "error"}`. It reads the workspace, which the webhooks and the reconciliation keep up to date. |
| `POST /organizations/domain/remove` | Asks the service to delete the domain, then clears the domain and its status fields. When the service cannot be reached the domain is kept and the page shows the error, so that nothing stays configured without an owner. |

The status moves through `pending`, `dns_verifying`, `dns_verified`,
`ssl_provisioning` and `active`, or `failed`, as the service progresses (see
[Custom domains](13-custom-domains.md)); the page polls the status endpoint to
show the progress without reloading.

## Settings

The page uses `CUSTOM_DOMAIN_CNAME_TARGET` (shown before a domain is registered); the
service, its client and the webhook secret are described on the custom domains page.

## Navigation

The page is reached from the *Enterprise Features* card of the settings page (*Configure*),
which only Enterprise workspaces see. It belongs to the settings: the *General* item of the
sidebar is the active one.

## Tests

pytest (`test_web_organizations.py`, the part covering these routes): the page
for every plan and role, the update with validation, conflicts, the replacement of a
domain and the refusals of the service, the retry (restart, legacy registration, error),
the status endpoint and the removal (with the service down).

behave (`features/workspace_domain.feature`): real routes and templates over the
in-memory store, with the custom-domain service replaced by a recorder.

- Administrators of an Enterprise workspace see the domain page
- Other plans are sent back to the settings
- Regular members cannot see the domain page
- Setting a domain registers it in the custom-domain service
- Replacing the domain removes the previous one from the service
- The service refuses the domain
- The service is down
- An invalid domain is refused
- A domain used by another workspace is refused
- The status endpoint reports that there is no domain
- The status endpoint reports the provisioning progress
- Retrying the verification asks the service
- Retrying registers a domain the service never knew
- Removing the domain clears it and asks the service to remove it
- The domain is kept when the service cannot remove it

browser (`features/workspace_domain.feature` in `features/browser/`, tag `@browser`): the pages in a
real Chromium, signed in through the fake OpenID provider, over a SQLite file. The custom-domain
service is an in-memory fake that records the registrations, verifications and removals and can
be told to refuse or to be down; the status that the service would report through its webhooks
is written to the database. Every link of the pages is followed to check that it leads to a page.

- The settings of an Enterprise workspace lead to the custom domain page
- A domain is registered in the custom-domain service
- The verification of the DNS can be retried
- An active domain is shown with its address
- The domain is removed
- A badly formed domain is refused
- A domain of another workspace is refused
- The service refusing a domain is explained
- A service that is down is reported without losing the page
- Only Enterprise workspaces can use a custom domain
- A regular member cannot configure the domain
- The custom domain pages only lead to pages that exist
