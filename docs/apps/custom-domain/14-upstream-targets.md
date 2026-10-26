# TCP upstream targets

A domain is served by forwarding its requests to an application, the
*upstream*. Until now the upstream had to be a Unix socket. This feature lets it
be a TCP address as well, so an application that listens on `host:port` (another
host of the private network, a container, a service bound to a port) can be
served, and it validates every target before it reaches generated nginx
configuration.

## What a target is

`upstream_target` is one of:

| Form | Example | nginx directive rendered |
| --- | --- | --- |
| Absolute socket path | `/run/app/app.sock` | `server unix:/run/app/app.sock;` |
| Socket path with the `unix:` prefix | `unix:/run/app/app.sock` | `server unix:/run/app/app.sock;` |
| Host name and port | `app.internal:8000` | `server app.internal:8000;` |
| IPv4 address and port | `10.0.0.5:8000` | `server 10.0.0.5:8000;` |
| IPv6 address in brackets and port | `[::1]:8000` | `server [::1]:8000;` |

Anything else is refused: URLs (`http://...`), a host without a port, a port
outside 1-65535, whitespace, `;`, `{`, `}`, `$`, quotes and `..` in a socket path.
The check is `custom_domain.services.upstream.parse_upstream`; it exists because
the target is written into an nginx file that root loads, so the previous
unchecked text was a configuration injection risk. Traffic to a TCP upstream is
plain HTTP (the TLS of the customer's domain ends at nginx); put the upstream on a
private network.

## Where it is checked

- Request bodies: `upstream_target` of `POST /domains` and `PUT /domains/{id}`,
  `default_upstream_target` of `POST` and `PUT /admin/clients`. An invalid value
  answers `422`.
- `POST /domains` also checks the value it resolved from the client default (a
  client created before this check may hold an invalid one) and answers `400
  Invalid upstream target: ...`.
- `custom-domain create-client --upstream` refuses an invalid value before it
  touches the database.
- The nginx context: rendering a domain whose stored target is invalid fails, and
  the provisioning task marks the domain `failed` with the reason.

## Template context

The default HTTPS template now renders `server {{ upstream_server }};`. Templates
receive three variables for the upstream:

| Variable | Value |
| --- | --- |
| `upstream_target` | The target as stored (unchanged, for existing custom templates). |
| `upstream_server` | The value for an nginx `server` directive: `unix:<path>` for a socket, `host:port` for TCP. |
| `upstream_type` | `unix` or `tcp`. |

A custom template that hard-codes `server unix:{{ upstream_target }};` keeps
working for socket targets only; use `{{ upstream_server }}` to support both. The
default template used to render `unix:` twice for a target written `unix:/path`;
that is fixed.

## Settings

None: the forms above are fixed by nginx's `server` syntax.

## How it is tested

- pytest: `test_services_upstream.py` (every accepted form, normalization of the
  port, and the rejected ones including injection attempts), `test_schemas.py`
  (`TestUpstreamValidation` for the domain and client schemas),
  `test_services_nginx.py` (`TestUpstreamInTheContext`, the rendered default
  template for both kinds), `test_routes_domains_scoping.py` (an invalid client
  default) and `test_cli.py` (the `--upstream` option).
- behave: `features/upstream_targets.feature` renders the default configuration
  for a socket and a TCP target, registers and updates domains with TCP
  upstreams, refuses an injection attempt, a URL and an invalid client default
  through the API, and refuses an invalid `--upstream` on the command line.
