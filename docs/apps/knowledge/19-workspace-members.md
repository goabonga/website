# Workspace members and invitations

Workspace administrators manage who belongs to the workspace and with which
role. The routes are part of `knowledge.routes.web.organizations`, mounted
under `/organizations` (and `/tenants` for old links) in the internal
sub-application, and rendered with the `tenants/` templates (`members`,
`invite`, `invite_view`, `invite_error`).

## Roles

`OrganizationMemberRole`: `owner`, `admin`, `member`. Owners and admins are
"administrators" (`is_tenant_admin`); only owners are `is_tenant_owner`.
Administrator pages answer `403` (`errors/403.html`) to regular members, and the
POST actions redirect non-administrators to `/dashboard`.

## Administration routes

| Route | Behavior |
| --- | --- |
| `GET /organizations/members` | Members (oldest first) and the pending, non-expired invitations. |
| `GET`/`POST /organizations/invite` | Invitation form. The email is stored lowercase with a random token (32 bytes, URL-safe) valid for 7 days; an unknown role becomes `member`, and an administrator who asks for `owner` gets `admin`. A second pending invitation for the same address re-displays the form with an error. After creation the `send_workspace_invitation_email` Celery task is queued (see [Background tasks](12-background-tasks.md)) with a link `<APP_BASE_URL>/tenants/invites/<token>`, then the browser goes back to the member list. |
| `POST /organizations/invitations/{id}/resend` | Queues the invitation email again for a pending, non-expired invitation. |
| `POST /organizations/invitations/{id}/revoke` | Marks a pending invitation `revoked`. |
| `POST /organizations/members/{id}/role` | Changes a member's role. Nobody can change their own role, an invalid role is ignored and only an owner can grant `owner` (an administrator's request is downgraded to `admin`). |
| `POST /organizations/members/{id}/remove` | Removes a member. Nobody can remove themselves and only an owner can remove an owner. |

All of them redirect back to `/organizations/members` when they are done.

## Public invitation pages

| Route | Behavior |
| --- | --- |
| `GET /organizations/invites/{token}` | Shows the invitation (workspace, role) to anyone. Unknown tokens, and invitations that are not pending any more, are explained on `invite_error.html`; a pending invitation whose date has passed is marked `expired` and reported as expired. When the visitor's cookie holds a valid token, the page greets them by name. |
| `POST /organizations/invites/{token}/accept` | Requires a valid session: otherwise it redirects to `/auth/login?redirect=/organizations/invites/<token>`. It creates the membership with the invited role (or keeps the existing one), marks the invitation `accepted`, sets the `active_tenant_id` cookie and redirects to `/dashboard`. Invalid, used or expired invitations go back to the invitation page. |

A visitor who is not signed in is offered *Sign In to Accept* (`/auth/login?redirect=<invitation>`)
and *Create an Account* (`/auth/signup?redirect=<invitation>`); both bring the invitee back to
the invitation page once signed in. For a workspace administrator the sidebar gains the *Members*
item (active on the members and invitation form pages) and the dashboard a *Team Members* quick
action.

## Tests

pytest (`test_web_organizations.py`, the part covering these routes): the member
list, form, creation (roles, duplicates, email task), resend, revoke, role
changes and removals with every guard, and the public view and accept routes.

behave (`features/workspace_members.feature`): real routes and templates, an
in-memory store, a recording stand-in for the email task and a fake token
validator.

- Administrators see the members and pending invitations
- Regular members cannot see the member list
- Inviting someone stores an invitation and queues the email
- An administrator cannot invite an owner
- A pending invitation is not duplicated
- Resending an invitation queues the email again
- Revoking an invitation
- Changing a member's role
- An administrator cannot promote someone to owner
- Nobody can change their own role
- Removing a member
- An administrator cannot remove the owner
- A pending invitation can be viewed by anyone
- A revoked invitation is reported
- An expired invitation is reported and marked
- An unknown invitation is reported
- Accepting an invitation requires signing in
- A signed-in user accepts an invitation

browser (`features/workspace_members.feature` in `features/browser/`, tag `@browser`): the
pages in a real Chromium, signed in through the fake OpenID provider, over a SQLite file. The
invitation emails are sent by the real Celery task, run synchronously, through a fake of the
mailler service that keeps them like a mailbox: the scenarios open the link of the email as its
recipient would. Every link of the pages is followed to check that it leads to a page.

- The members page lists the team and offers to invite
- An invitation is sent by email and listed as pending
- The same person cannot be invited twice at once
- An invitation is resent or revoked
- An invitee follows the link of the email, signs in and joins
- An invitee without account is offered to sign up
- An unknown invitation is reported
- An expired invitation is reported
- The role of a member is changed and the member is removed
- A regular member cannot manage the team
- The members pages only lead to pages that exist
