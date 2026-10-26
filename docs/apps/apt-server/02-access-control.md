# Access control rules

Access to the repository is decided by three layers applied from the top
down. This feature introduces the first two, which only depend on settings
and on the scopes of the caller. The third one, the per-package ACL, is
documented with the package catalog.

## Layer 1: component visibility

A repository is split into components (`main`, `private`, ...). Two settings
describe them:

| Variable | Default | Description |
| --- | --- | --- |
| `APT_COMPONENTS` | `main` | Comma-separated components that exist |
| `APT_PUBLIC_COMPONENTS` | `main` | Components readable without credentials |

`apt_server.acl.components` exposes `is_known_component`,
`is_public_component`, `known_components` and `public_components` (the last
two return copies). Whitespace and empty items in the lists are ignored. A
component that is not known is never served.

## Layer 2: OAuth2 scopes

Scopes come from the token introspection response (see the OIDC
authentication page) and gate the API. `apt_server.acl.scopes` implements the
hierarchy:

```
apt:admin       implies apt:write      implies apt:read
apt:write       implies apt:write:<c>  implies apt:read
apt:write:<c>   implies apt:read:<c>   implies apt:read
```

| Function | True when |
| --- | --- |
| `parse_scopes(raw)` | normalises a space separated string or a list into a set |
| `has_admin(scopes)` | `apt:admin` is present |
| `may_read(scopes)` | any `apt:` read or write scope, or admin |
| `may_write(scopes, component)` | admin, `apt:write`, or `apt:write:<component>` |
| `may_reindex(scopes)` | admin only |

Unrelated scopes (`openid`, `profile`, ...) grant nothing: a caller holding
only those is treated like an anonymous one.

The module has no HTTP surface yet; the rules are consumed by the APT
endpoints and the package API of the following features.

## Tests

- pytest: `tests/test_scopes.py` (parsing, admin, global and component
  write, read-only, unrelated scopes) and `tests/test_components.py`
  (known and public components, copies, list parsing, defaults).
- behave: `features/access_control.feature` with the scenarios "Anonymous
  callers only see public components", "Administrators may do everything",
  "A global write scope covers every component", "A component write scope is
  limited to that component", "A read scope does not allow uploads" and "A
  caller without apt scopes is treated as anonymous". The rules are evaluated
  in-process, no HTTP involved.
