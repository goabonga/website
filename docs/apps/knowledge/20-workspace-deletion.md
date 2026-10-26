# Workspace deletion

Deleting a workspace is irreversible, so it takes two steps and an email. The
routes are part of `knowledge.routes.web.organizations` (mounted under
`/organizations`, see [Workspace settings and plans](18-workspace-settings.md))
and persist their state in `workspace_deletion_requests` (see the [data
model](01-data-model.md)). The emails and the periodic jobs that complete the
flow are described in [Background tasks](12-background-tasks.md).

## Flow

1. **Request** (`POST /organizations/delete`). Only the owner can ask (others
   get the `403` page). The owner types the exact workspace name; a mismatch
   re-displays the settings page with an error. Otherwise any previous pending
   request of the workspace is cancelled, a new request is stored (24-hour
   expiry, random token) and `send_workspace_deletion_email` is queued with the
   link `<APP_BASE_URL>/organizations/delete/confirm/<token>`. The browser is
   shown `deletion_requested.html`.
2. **Confirmation page** (`GET /organizations/delete/confirm/{token}`), reached
   from the email by a signed-in user. It shows the workspace and the expiry, or
   an explanation (`deletion_error.html`) when the link is unknown, expired (the
   request is then marked `expired`), already used or when the workspace no
   longer exists.
3. **Execution** (`POST /organizations/delete/confirm/{token}`). The billing
   service is asked for the workspace subscription (see [Billing
   integration](09-billing.md)).
   - With an active or trialing subscription whose period ends in the future,
     the subscription is cancelled at period end, the request becomes
     `scheduled` for that date (with a cancellation token) and
     `send_workspace_deletion_scheduled_email` is queued. The workspace stays
     usable until then and `deletion_scheduled.html` is shown.
   - Otherwise (no subscription, billing not configured, or the cancellation
     failed) the workspace is deleted immediately: the request becomes
     `confirmed`, the organization is deleted (its collections, documents,
     members and invitations go with it) and `send_workspace_deleted_email` is
     queued. If the requester still belongs to a workspace they return to
     `/dashboard?deleted=true` with the active workspace cookie removed;
     otherwise they are signed out through `/auth/logout`.
4. **Scheduled deletion**. The hourly `process_scheduled_deletions` task deletes
   the workspaces whose date has passed, and `send_deletion_reminders` queues a
   reminder email one day before, with the cancellation link.
5. **Cancellation** (`GET /organizations/delete/cancel/{cancel_token}`). While
   the request is `scheduled`, the link reactivates the subscription if it had
   been cancelled and marks the request `cancelled` (`deletion_cancelled.html`).
   Other states are explained on the error page.

Request states (`DeletionRequestStatus`): `pending`, `confirmed`, `scheduled`,
`cancelled`, `expired`.

The confirmation and cancellation routes require a signed-in user but do not
check that this user is the requester: possession of the emailed token is what
authorizes them.

## Templates

`tenants/deletion_requested.html`, `deletion_confirm.html`,
`deletion_scheduled.html`, `deletion_cancelled.html` and `deletion_error.html`.

The *Danger Zone* card of the settings page carries the request form for the owner; an
administrator sees the button disabled with the reason.

## Tests

pytest (`test_web_organizations.py`, the part covering these routes): the
request with its guards, the confirmation page for every request state,
immediate and scheduled execution including billing failures, redirects after
deletion, and cancellation.

behave (`features/workspace_deletion.feature`): real routes, templates and
deletion request model over the in-memory store, with recording email stand-ins
and the fake billing client.

- Only the owner can request a deletion
- The workspace name must be typed exactly
- A confirmed name creates a request and sends the confirmation email
- A new request cancels the previous pending one
- The confirmation page shows the workspace to delete
- An unknown confirmation link is reported
- An expired confirmation link is reported and marked
- Confirming deletes a workspace without subscription at once
- Deleting the last workspace signs the user out
- A paid workspace is scheduled for the end of the billing period
- Cancelling a scheduled deletion reactivates the subscription
- A cancellation link works only for scheduled deletions
- Deletion pages require a signed-in user

browser (`features/workspace_deletion.feature` in `features/browser/`, tag `@browser`): the flow
in a real Chromium, signed in through the fake OpenID provider, over a SQLite file. The three
emails are sent by the real Celery tasks, run synchronously, through a fake of the mailler
service; the scenarios follow the link of the confirmation email like its recipient. The billing
service is an in-memory fake whose subscription decides between immediate and scheduled
deletion. Every link of the pages is followed to check that it leads to a page.

- The owner asks for the deletion and gets an email to confirm it
- The name of the workspace has to be typed exactly
- The deletion is carried out from the link of the email
- Deleting the only workspace signs the owner out
- A workspace with a subscription is deleted at the end of the period
- A link that is not valid is reported
- A link used twice is reported
- An administrator cannot delete the workspace
- The deletion pages only lead to pages that exist
