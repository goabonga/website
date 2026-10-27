# Scopes and roles of the platform services

The services of the platform check scopes that `auth`, the authentication server,
stores (`billing:read`, `mailler:send`, ...), and roles that group them. These
names are deployment data, not behaviour of `auth`: they are not written in its
code or its migrations. Each application states what it needs in its catalog
entry, and the `python_app` role merges the statements of the enabled
applications into one JSON file that `auth` reads.

## What an application declares

The primary component of an application may carry an `auth_catalog` key (see
the [component reference](roles/python_app.md#component-reference)):

```yaml
website_apps_overrides:
  notes:
    auth_catalog:
      scopes:
        - {name: "notes:read", description: "Read notes"}
        - {name: "notes:write", description: "Write notes", category: app}
      roles:
        - name: notes_editor
          description: Edit notes
          scopes: ["notes:read", "notes:write"]
      clients:
        - client_id: "{{ website_oauth2_clients.notes.client_id | default('') }}"
          allowed_scopes: ["notes:read"]
          allowed_grant_types: [client_credentials]
      scope_groups:
        "suite:*": [notes]
```

| Key | Content |
| --- | --- |
| `scopes` | `name` (required), `description`, `category` (`api` by default), `resource`, `action`, `is_system`, `is_active`; see [the catalog of auth](../apps/auth/19-catalog.md) for the defaults. |
| `roles` | `name` (required), `description`, `scopes` (names), `is_system`. A role may add scopes to a role of another application or to a built-in role. |
| `clients` | `client_id`, `allowed_scopes`, `allowed_grant_types`: allowances added to an **existing** OAuth2 client. An entry whose `client_id` is empty is ignored, so that the identifier can come from `website_oauth2_clients`, which the inventory fills. |
| `scope_groups` | A group scope and the resources it stands for (`SCOPE_GROUPS` of `auth`): a client allowed the group may be granted any scope of these resources in a token exchange. |

Every key is optional. An application that declares nothing adds nothing.

## How the file is made

When `auth` is deployed, the role merges, in the order of the catalog, the
`auth_catalog` of every component of the applications in `website_apps_enabled`
(not only of those of this run, so that limiting a run to `auth` renders the same
file), then `website_auth_catalog`, which has the same shape and is the place
for what the inventory adds:

- a scope declared by several sources is one scope; the later declaration
  overrides the fields it sets;
- the scopes of a role named by several sources, and the allowances of a client,
  are added together;
- the result is sorted, so that the file only changes when its content does.

The file is written to `website_auth_catalog_file` (`/opt/auth/catalog.json` by
default, mode `0640`, owned by the account of `auth`) and the environment file of
`auth` points to it with `CATALOG_FILE`; the group scopes go to `SCOPE_GROUPS`.
To apply it to the database, run `auth catalog sync` after the migrations (see
[the catalog of auth](../apps/auth/19-catalog.md)).

A role may only list scopes that exist: declare a scope in the application that
owns the role, even when another application declares it too (identical
declarations are merged).

## Checks

The role stops before changing anything when an `auth_catalog` is malformed: the
scopes, roles and clients must be lists, `scope_groups` a dictionary, every scope
and role needs a `name`, the scopes of a role must be a list and every client
needs a `client_id` key.
