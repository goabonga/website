# Nginx configuration rendering

Each custom domain is served by its own nginx virtual host. This feature adds
the two services that produce and manage those files: `template_service`
(Jinja2 rendering and validation) and `nginx_manager` (writing, removing and
reloading configuration). It also ships the two default templates. Nothing is
exposed over HTTP yet; the provisioning feature drives these services.

## Templates

A domain goes through two configurations:

1. **HTTP only** (`templates/nginx_http.conf.j2`): listens on port 80 for
   the domain, serves `/.well-known/acme-challenge/` from the certbot webroot
   and redirects everything else to HTTPS. It is written first so that the
   ACME challenge can succeed.
2. **HTTPS** (`templates/nginx_https.conf.j2`): defines an `upstream`
   pointing at the domain's upstream (`server {{ upstream_server }};`: a Unix
   socket or a TCP address, see the TCP upstream targets page),
   keeps the port 80 block, and adds a `443 ssl http2` server with the
   Let's Encrypt certificate, modern TLS settings, HSTS and security headers,
   WebSocket-aware proxying and a `/health` location.

Custom templates (stored in the database, see the template administration
feature) replace either file. Every template receives the same context:

| Variable | Value |
| --- | --- |
| `domain` | The domain name. |
| `upstream_target` | The domain's upstream as stored. |
| `upstream_server`, `upstream_type` | The `server` directive value for that upstream and its kind (`unix` or `tcp`). |
| `certbot_webroot` | `CERTBOT_WEBROOT`. |
| `ssl_certificate`, `ssl_certificate_key` | `<LETSENCRYPT_DIR>/live/<domain>/fullchain.pem` and `privkey.pem`. |
| `nginx_ipv4`, `nginx_ipv6` | `NGINX_IPV4` and `NGINX_IPV6` (may be `None`). The default templates do not use them. |
| `client_id`, `owner_id` | Identifiers of the owning client and tenant. |
| `metadata` | The domain's metadata dictionary (empty when unset). |

## Services

### `template_service`

- `render_default_http(context)` / `render_default_https(context)` render the
  files above with a Jinja2 environment that has autoescaping off and
  `trim_blocks` / `lstrip_blocks` on.
- `render_template(source, context)` renders a template stored in the
  database.
- `validate_template(source, test_context=None)` compiles the source and, when
  a context is given, renders it. It returns a `TemplateValidationResult` with
  `valid`, `errors` (for example `Syntax error at line 2: ...`) and the
  rendered output.
- `validate_nginx_syntax(config)` stages the text as `validate-<token>.conf`
  and asks the privileged helper to run `nginx -t` on it. The helper wraps the
  text in the `events` and `http` contexts that a virtual host needs to be
  tested alone, so a fragment made only of `server` blocks can be checked. The
  certificate files named by the text must exist for nginx to accept it, so use
  the result as a hint, not as a guarantee. It returns `(False, <message>)`
  instead of raising when the deployment is not configured. The call needs the
  helper, so it must run in a worker (template administration page).
- `get_template(db, template_id=None)` loads a template by id, or the active
  default template.

### `nginx_manager`

- `generate_http_config(domain, template=None)` and
  `generate_https_config(domain, template=None)` build the context and render
  the custom template when one is given, the default file otherwise.
- `write_config(domain, config)` stages the file as
  `<PRIVILEGED_STAGING_DIR>/<NGINX_CONFIG_PREFIX><domain>.conf`, asks the
  helper to install it as `<NGINX_SITES_DIR>/<NGINX_CONFIG_PREFIX><domain>.conf`
  and removes the staged copy.
- `remove_config(domain)` asks the helper to remove that file (nothing happens
  when it does not exist).
- `test_config()` asks the helper to run `nginx -t`; `reload()` tests first and
  then reloads nginx through systemd. `write_config`, `remove_config` and
  `reload` raise `RuntimeError` on failure.

## Privileged operations

The API and the worker run as an ordinary system user. The only thing this
service starts with `sudo` is one small script, `custom_domain/privileged_helper.py`,
through `custom_domain.services.privileged.run_privileged`. The script is a
single-file, standard-library program that is installed once, owned by root with
mode `0755`, at the path given by `PRIVILEGED_HELPER`. It accepts a fixed set of
commands and nothing else:

| Command | Argument | What it does |
| --- | --- | --- |
| `write-config` | domain | Copies `<staging>/<prefix><domain>.conf` to `<sites>/<prefix><domain>.conf` (root-owned, mode `0644`, replaced atomically). |
| `remove-config` | domain | Removes `<sites>/<prefix><domain>.conf` if present. |
| `test-nginx` | none | Runs `<nginx> -t`. |
| `reload-nginx` | none | Runs `<systemctl> reload <nginx service>`. |
| `check-snippet` | 32-character hexadecimal token | Wraps the staged `validate-<token>.conf` in `events`/`http` and runs `<nginx> -t -c` on it. |

Every call is `sudo -n <helper> <options> <command> [<argument>]`. The options
(`--sites-dir`, `--config-prefix`, `--staging-dir`, `--nginx-bin`,
`--nginx-service`, `--systemctl-bin`) come from the settings, so the sudoers rule
that allows the helper fixes their values and the caller can not change them. The
helper rejects anything that is not exactly the expected option set, validates the
paths (absolute and normalized), the file prefix and the unit name, accepts only a
lower-case domain name or a hexadecimal token as the argument, derives every file
name itself, reads staged files without following symbolic links and with a size
limit, refuses executables that are not owned by root when it runs as root, and
starts the programs with a reduced environment.

The sudoers rules are generated from the same table:

```bash
python -m custom_domain.services.privileged --user <worker user>
```

prints one rule per command, built from the current settings. Commands without
an argument are one exact command line; commands with a domain or token end
with `*`, which only has to match that one validated argument. The deployment
page lists the complete set once the certificate commands exist.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `NGINX_SITES_DIR` | empty (required) | Directory that receives the generated files. |
| `NGINX_CONFIG_PREFIX` | `custom-domain-` | Prefix of the generated file names. |
| `NGINX_IPV4`, `NGINX_IPV6` | unset | Server addresses exposed to templates. |
| `NGINX_BIN` | empty (required) | Absolute path of the `nginx` binary run by the helper. |
| `NGINX_SERVICE` | `nginx` | systemd unit reloaded by the helper. |
| `SYSTEMCTL_BIN` | empty (required) | Absolute path of `systemctl`. |
| `CERTBOT_WEBROOT` | empty (required) | Webroot of the ACME challenge, used by the default templates. |
| `LETSENCRYPT_DIR` | empty (required) | Directory that holds `live/<domain>/` certificates; used for `ssl_certificate` and `ssl_certificate_key`. |
| `SUDO_BIN` | `sudo` | Command used to start the helper. |
| `PRIVILEGED_HELPER` | empty (required) | Absolute path of the installed helper script. |
| `PRIVILEGED_STAGING_DIR` | empty (required) | Directory writable by the service user where files are staged for the helper. |
| `PRIVILEGED_TIMEOUT_SECONDS` | `120` | Time after which a helper call is killed. |
| `TEMPLATES_DIR` | `custom_domain/templates` | Directory of the default templates, relative to the directory that contains the package. |

Settings marked required have no default on purpose: an empty value makes the
operation that needs it fail with a message naming the variable
(`ConfigurationError`), instead of writing to a guessed location.

## How it is tested

- pytest: `test_services_template.py` (default and custom rendering,
  validation errors, template lookup, nginx syntax check),
  `test_services_nginx.py` (file naming, context, rendering, write / remove /
  test / reload with the helper calls mocked), `test_services_privileged.py`
  (command lines, missing settings, timeout, staging, sudoers rules and their
  consistency with the commands the application runs) and
  `test_privileged_helper.py`, which runs the real helper against temporary
  directories and fake `nginx`/`systemctl` programs: command-line validation,
  installation, symbolic links, size limit, removal, the snippet wrapper and
  the reduced environment.
- behave: `features/nginx_rendering.feature` with *The default HTTP
  configuration serves the ACME challenge*, *The default HTTPS configuration
  proxies to the upstream socket*, *A custom template replaces the default
  one*, *A template with a syntax error is reported with its line*, *A valid
  template is rendered with test variables*, *A configuration is installed by
  the privileged helper*, *A configuration is removed by the privileged helper*,
  *Reloading nginx tests the configuration first* and *The sudoers rules are
  generated from the same commands*. The system commands are recorded instead of
  executed, so nothing touches nginx or the file system apart from the temporary
  staging directory.

Not verified: the helper has not been run as root against a real nginx or with
a real `sudoers` file.
