# python_app

Deploys the platform applications from the monorepo. Applications are not
published to PyPI or packaged for Debian: the role checks the repository out,
installs the dependencies of one workspace member into its own virtualenv with
uv, writes its environment file and encrypted credentials, and runs it as a
hardened systemd service. It can also create the PostgreSQL database, run the
Alembic migrations, publish the service through nginx with a certificate,
rate-limit routes with fail2ban, hook an Asterisk dialplan or an OpenVPN
server to it, and configure AWS SES notifications.

The applications to deploy are chosen with `website_apps_enabled`. What each
one consists of comes from a catalog of components
(`website_apps_catalog`), adjustable with `website_apps_overrides`. The catalog
and the override rules are explained in [Deploying applications](../05-deploying-apps.md).

## Requirements

- Debian 12 or 13, Ubuntu 22.04 or 24.04, with systemd 250 or later (encrypted
  credentials).
- Privilege escalation (`become: true`).
- Collections `community.postgresql` (databases) and `ansible.posix`, both
  dependencies of `goabonga.website`.
- Outbound access to the Git server and to the Python package index during a
  deployment.
- For the optional parts, the matching roles run first: `postgres`, `redis`,
  `nginx`, `certbot`, `fail2ban`, `dnsmasq`, `step_ca_client`, `asterisk` and
  `openvpn`. The role checks for what it needs and stops with a message when
  something is missing.

## Usage

```yaml
- hosts: web
  become: true
  roles:
    - role: goabonga.website.python_app
      vars:
        website_domain: example.com
        website_apps_enabled: [frontend, backend]
        website_secrets:
          backend:
            OPENAI_API_KEY: "{{ vault_openai_api_key }}"
            OAUTH2_CLIENT_SECRET: "{{ vault_backend_oauth2_client_secret }}"
```

The playbook `goabonga.website.apps` runs this role. Deploy a subset of the
enabled applications with `-e '{"website_apps_limit": ["backend"]}'`.

## What it does

1. Validates the selection: every enabled application must exist in the
   catalog, component types must be known, unit names must be unique.
2. Installs the system packages (and Node.js when a component builds a web
   client), installs uv in `<website_state_dir>/tools`, and clones or updates
   the monorepo in `<website_state_dir>/repo` (a private repository is reached
   with `website_repo_token`; the clone is readable by root only).
3. For each application, creates the system account and group, adds the
   account to the groups of the sockets it needs (PostgreSQL, Redis, the
   applications listed in `extra_groups`, the step group) and writes its sudo
   rules. Groups that do not exist on the host are skipped with a message.
4. For each application, resolves the version (`version` of the primary
   component, else `website_repo_version`; branch, tag or commit) to a commit,
   extracts that commit into `<dir>/releases/<commit>`, points `<dir>/current`
   at it and runs `uv sync --frozen --no-dev --package <name>` into
   `<dir>/venv`. Older releases beyond `website_keep_releases` are removed.
5. For each component of the application (primary first): writes the
   environment file and the encrypted credentials, runs the `build_commands`
   once per release, runs the migrations, writes the gunicorn configuration
   and the unit, enables and starts the unit, and restarts it when the
   release, the environment, a credential or the unit changed.
6. Sets up the optional parts declared by the component: database,
   nginx virtual host and certificate, fail2ban jails, Asterisk dialplan,
   OpenVPN hooks, SES notifications.
7. Writes the log rotation of the application and the nightly database
   backup.

## Layout on the host

For an application whose primary component is named `auth`:

| Path | Content |
| --- | --- |
| `/opt/auth/releases/<commit>/` | Extracted release of the monorepo. |
| `/opt/auth/current` | Link to the active release; the working directory of the units. |
| `/opt/auth/venv/` | Virtualenv shared by the components of the application. |
| `/opt/auth/env/<unit>.env` | Environment file of a component (mode 0600). |
| `/opt/auth/env/<unit>.gunicorn.py` | Gunicorn configuration of a web component. |
| `/opt/auth/logs/` | `<unit>.log` and `<unit>-error.log` of every unit, and `nginx/` for the access and error logs of the virtual host. |
| `/opt/auth/bin/` | Wrapper scripts of the `script` components. |
| `/opt/auth/backups/` | Database dumps. |
| `/etc/credstore.encrypted/<unit>.<NAME>.cred` | Encrypted credentials of a unit. |
| `/etc/systemd/system/<unit>.service` | Unit of a component. |
| `/run/<unit>/<unit>.sock` | Unix socket of a web component. |
| `/var/lib/website/` | Shared clone (`repo/`), uv (`tools/`). |

The directory is named after the primary component; the account and group
have the same name unless `user` and `group` are set.

## Variables

Every variable is optional and defined in `defaults/main/`. The role validates
them against `meta/argument_specs.yml` before running.

### Application selection

| Variable | Default | Description |
| --- | --- | --- |
| `website_apps_enabled` | `[]` | Applications to deploy, by catalog application name (for example auth, backend, frontend). An application brings every component of the catalog that belongs to it (web service, worker, beat, scripts). |
| `website_apps_limit` | `[]` | Optional subset of website_apps_enabled to deploy on this run. Empty means every enabled application. |
| `website_apps_overrides` | `{}` | Deep-merged over the catalog, keyed by component (auth, auth_worker, ...). Use it to pin a version, change a setting or define extra components. |

### Source of the applications

| Variable | Default | Description |
| --- | --- | --- |
| `website_repo_url` | `"https://github.com/goabonga/website.git"` | Git URL of the monorepo. Applications are deployed from this repository; nothing is published to PyPI or built as a Debian package. |
| `website_repo_version` | `"main"` | Branch, tag or commit deployed by default. Pin one application with website_apps_overrides.<application>.version. |
| `website_repo_token` | `""` | Access token for a private repository (HTTPS). Empty for a public one. |
| `website_state_dir` | `"/var/lib/website"` | Directory holding the shared clone of the monorepo and the uv installation. |
| `website_base_dir` | `"/opt"` | Parent of the per-application directories (<base>/<name>). |
| `website_keep_releases` | `3` | Number of releases kept on disk per application. |

### Python and uv

| Variable | Default | Description |
| --- | --- | --- |
| `website_uv_install_method` | `"pip"` | uv installation: pip installs it in a dedicated virtualenv under website_state_dir, none uses the binary found at website_uv_bin. |
| `website_uv_version` | `""` | uv version installed with the pip method (empty installs the latest). |
| `website_uv_bin` | `{{ website_state_dir }}/tools/bin/uv` | Path of the uv binary. |
| `website_python_version` | `""` | Python interpreter handed to uv (empty lets uv pick one matching the requires-python of the project). |
| `website_uv_python_preference` | `"system"` | Python selection policy of uv: system, managed, only-system or only-managed (UV_PYTHON_PREFERENCE). |
| `website_system_packages` | `["git", "python3", "python3-venv", "curl", "zstd"]` | Distribution packages needed to build and run the applications. |
| `website_node_install_method` | `"apt"` | How Node.js is installed when a component sets build_node: apt, nodesource or none. |
| `website_node_version` | `"20"` | Major Node.js version installed by the nodesource method. |

### Runtime behaviour

| Variable | Default | Description |
| --- | --- | --- |
| `website_hardening_enabled` | `true` | Apply systemd hardening to every unit (per-component override available). |
| `website_secrets_required` | `true` | Fail when a required secret is missing instead of deploying without it. |
| `website_secrets` | `{}` | Secrets, keyed by application or component name then by variable name: website_secrets: {auth: {JWKS_ENCRYPTION_KEY: <value from a vault>}} Component-level entries win over application-level ones. The values are stored as encrypted systemd credentials and never written to the environment file. |
| `website_credstore_dir` | `"/etc/credstore.encrypted"` | Directory holding the encrypted systemd credentials. |
| `website_redis_group` | `"redis"` | Name of the group that owns the Redis socket. |

### Neighbouring services

| Variable | Default | Description |
| --- | --- | --- |
| `website_redis_socket` | `{{ redis_socket \| default('') }}` | Redis Unix socket (follows the redis role); an empty value selects TCP. |
| `website_redis_host` | `"127.0.0.1"` | Redis host, used when there is no socket. |
| `website_redis_port` | `6379` | Redis TCP port, used when there is no socket. |
| `website_redis_password` | `""` | Redis password, used when there is no socket (empty for none). |
| `website_redis_url` | `{{ 'unix://' ~ website_redis_socket    if website_redis_socket \| length > 0    else 'redis://' ~ (':' ~ website_redis_password ~ '@' if website_redis_password \| length > 0 else '')         ~ website_redis_host ~ ':' ~ website_redis_port }}` | Redis URL for clients that accept the unix:// scheme. |
| `website_celery_redis_url` | `{{ 'redis+socket://' ~ website_redis_socket    if website_redis_socket \| length > 0    else website_redis_url }}` | Redis URL for Celery, which needs the redis+socket:// scheme. |
| `website_celery_broker_url` | `{{ website_celery_redis_url ~ '?db=0' if website_redis_socket \| length > 0 else website_redis_url ~ '/0' }}` | Celery broker (Redis database 0). |
| `website_celery_result_backend` | `{{ website_celery_redis_url ~ '?db=1' if website_redis_socket \| length > 0 else website_redis_url ~ '/1' }}` | Celery result backend. |
| `website_smtp_host` | `"localhost"` | SMTP host handed to the applications that send mail directly. |
| `website_smtp_port` | `"587"` | SMTP port. |
| `website_smtp_tls` | `"true"` | Use TLS for SMTP ("true" or "false"). |
| `website_oauth2_issuer` | `https://{{ website_hostnames.auth }}` | Issuer shared by every application that validates tokens. |
| `website_oauth2_clients` | `{}` | OAuth2 client identifiers, keyed by application, for the components that set oauth2.enabled: website_oauth2_clients: backend: {client_id: "...", swagger_client_id: "..."} |

### Databases and migrations

| Variable | Default | Description |
| --- | --- | --- |
| `website_postgres_group` | `"postgres"` | Name of the group that owns the PostgreSQL socket. |
| `website_postgres_socket_dir` | `{{ postgres_socket_dir \| default('/var/run/postgresql') }}` | Directory of the PostgreSQL Unix socket (follows the postgres role). |
| `website_manage_databases` | `true` | Create the PostgreSQL roles and databases declared by the components. The postgres role (or an existing server) must be in place. |
| `website_run_migrations` | `true` | Run `alembic upgrade head` for the components that enable alembic. |

### Web front

| Variable | Default | Description |
| --- | --- | --- |
| `website_listen_ipv4` | `{{ (ansible_facts.get('default_ipv4') or {}).get('address', '') }}` | IPv4 address nginx listens on for public virtual hosts (empty listens on every address). |
| `website_listen_ipv6` | `{{ (ansible_facts.get('default_ipv6') or {}).get('address', '') }}` | IPv6 address nginx listens on for public virtual hosts (empty for none). |
| `website_internal_listen` | `"127.0.0.1"` | Address internal virtual hosts (zone website_internal_domain) listen on. |
| `website_internal_allowed_hosts` | `[]` | Networks allowed to reach the internal virtual hosts (empty allows every client that can reach website_internal_listen). A component overrides it with nginx.allowed_hosts. |
| `website_certbot_email` | `""` | Contact address for Let's Encrypt (admin@<domain> when empty). |
| `website_acme_webroot` | `"/var/www/html"` | Webroot used for the ACME HTTP-01 challenges. |
| `website_step_ca_acme_url` | `https://step-ca.{{ website_internal_domain }}/acme/acme/directory` | ACME directory of the internal CA used by the virtual hosts with ssl: step-ca. |
| `website_step_ca_root` | `"/etc/step-ca/certs/root_ca.crt"` | Root certificate of that CA. |
| `website_letsencrypt_dir` | `"/etc/letsencrypt"` | Directory of the Let's Encrypt certificates. |
| `website_nginx_error_pages_snippet` | `"/etc/nginx/snippets/error-pages.conf"` | nginx snippet with custom error pages, included only when the file exists. |
| `website_nginx_ssl_protocols` | `"TLSv1.2 TLSv1.3"` | TLS protocols of the virtual hosts. |
| `website_nginx_ssl_ciphers` | `"ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384"` | TLS ciphers of the virtual hosts. |
| `website_dnsmasq_dir` | `"/etc/dnsmasq.d"` | Configuration directory of the dnsmasq instance that resolves internal host names on the host. |
| `website_dnsmasq_vpn_dir` | `"/etc/dnsmasq-vpn.d"` | Configuration directory of the dnsmasq instance that serves the VPN clients, used only when it exists. |
| `website_aws_route53_access_key_id` | `""` | Route 53 access key id for wildcard certificates (ssl_dns_provider route53). |
| `website_aws_route53_secret_access_key` | `""` | Route 53 secret access key for wildcard certificates. |

### AWS SES

| Variable | Default | Description |
| --- | --- | --- |
| `website_aws_ses_access_key_id` | `""` | AWS access key id for the SES/SNS webhook configuration of the components that set ses_webhook. When empty the AWS CLI uses its own credential chain. |
| `website_aws_ses_secret_access_key` | `""` | AWS secret access key for the SES/SNS configuration. |

### OpenVPN hooks

| Variable | Default | Description |
| --- | --- | --- |
| `website_openvpn_server_conf` | `{{ openvpn_config_dir \| default('/etc/openvpn/server') }}/{{ openvpn_server_name \| default('server') }}.conf` | Configuration file of the OpenVPN server that calls the hook scripts of the script components (follows the openvpn role). |
| `website_openvpn_service` | `openvpn-server@{{ openvpn_server_name \| default('server') }}` | systemd unit of that server. |
| `website_apparmor_local_dir` | `"/etc/apparmor.d/local"` | Directory of the AppArmor local overrides. |

### Asterisk

| Variable | Default | Description |
| --- | --- | --- |
| `website_asterisk_config_dir` | `{{ asterisk_config_dir \| default('/etc/asterisk') }}` | Configuration directory of Asterisk (follows the asterisk role). |
| `website_asterisk_user` | `{{ asterisk_user \| default('asterisk') }}` | Account that owns the Asterisk configuration (follows the asterisk role). |
| `website_asterisk_group` | `{{ asterisk_group \| default('asterisk') }}` | Group that owns the Asterisk configuration (follows the asterisk role). |

### Host names

| Variable | Default | Description |
| --- | --- | --- |
| `website_domain` | `""` | Public DNS zone the applications are served under. There is no default: deploying an application with a public virtual host fails until it is set. |
| `website_internal_domain` | `"internal"` | Zone suffix of the applications that are only reachable internally. |
| `website_internal_apps` | `["billing", "custom_domain", "internal", "mailler", "reachy_mini_api", "team"]` | Applications served under website_internal_domain instead of website_domain. |
| `website_subdomains_defaults` | `{"analytics": "ua", "apt_server": "apt", "auth": "auth", "backend": "api", "billing": "billing", "custom_domain": "custom-domain", "frontend": "", "internal": "admin", "knowledge": "knowledge", "mailler": "mailler", "mta_sts": "mta-sts", "reachy_mini_api": "reachy", "team": "team", "vpn_portal": "vpn", "webhooks": "webhooks"}` | Label prepended to the zone for each application. An empty label serves the application on the bare zone. Override single entries with website_subdomains_overrides. |
| `website_subdomains_overrides` | `{}` | Labels merged over website_subdomains_defaults. |
| `website_subdomains` | *defaults merged with the overrides* | Labels in effect. |
| `website_hostnames_overrides` | `{}` | Complete host names that replace the derived ones, keyed by application. |
| `website_hostnames` | *derived* | Host name of each application: the label in front of the zone, or the bare zone for an empty label. The name is empty while the zone is empty, and the applications without an entry in website_subdomains (asterisk) have none. |

### Catalog

| Variable | Default | Description |
| --- | --- | --- |
| `website_apps_catalog` | the platform catalog | Components of the platform applications, keyed by component name. Replace it entirely to deploy something else. See [Deploying applications](../05-deploying-apps.md). |
| `python_app_component_defaults` | see below | Defaults every component is merged over. Not meant to be overridden. |

## Component reference

A catalog entry, an entry of `website_apps_overrides` and the defaults below are
deep-merged: dictionaries are merged key by key, lists and scalars are
replaced. A component only states what differs from the defaults.

The name of the entry is the component identifier. The primary component of an
application has the name of the application; the others set `app`.

### Identity and process

| Key | Default | Description |
| --- | --- | --- |
| `enabled` | `true` | Set to `false` to skip the component. The primary component cannot be disabled. |
| `app` | the entry name | Application the component belongs to. |
| `name` | the entry name with dashes | Unit name. The primary component's name gives the directory, account and group. |
| `module` | the application name | Import package (`apps/<name>/src/<module>`). |
| `package` | the application name with dashes | uv workspace package. |
| `type` | `gunicorn` | `gunicorn`, `celery_worker`, `celery_beat`, `daemon`, `audiosocket`, `fastagi` or `script`. |
| `version` | `website_repo_version` | Branch, tag or commit of the application (primary component only). |
| `user`, `group` | the primary component's name | Account and group of the application (primary component only). |
| `extra_groups` | `[]` | Groups the account joins, for the sockets of other applications (`/run/<group>` is writable in the unit). Merged for every component of the application. |
| `extra_path` | `[]` | Directories appended to `PATH`. |
| `sudoers` | `[]` | Commands the account may run through sudo without a password. `NoNewPrivileges` is lifted for the units of the components that set it. |
| `stepca_group_member` | `false` | Join the `step` group to read the provisioner password. |
| `healthcheck.enabled` | `false` | The unit only counts as started once the probe answers. |
| `healthcheck.path` | `/health` | Path of the probe. |
| `healthcheck.timeout` | `10` | Seconds to wait. |
| `oauth2.enabled` | `false` | Generate `OAUTH2_ISSUER` from `website_oauth2_issuer`, and `OAUTH2_CLIENT_ID`, `OAUTH2_SWAGGER_CLIENT_ID` and `OAUTH2_FRONTEND_CLIENT_ID` from `website_oauth2_clients.<app>` (`client_id`, `swagger_client_id`, `frontend_client_id`). |
| `env_vars` | `{}` | Content of the environment file, merged over the generated variables. Lists and dictionaries are written as JSON. |
| `secret_names` | `[]` | Secrets that must be provided through `website_secrets`. |
| `optional_secret_names` | `[]` | Secrets deployed only when provided. |
| `hardening.enabled` | `true` | Systemd sandboxing of the unit (also gated by `website_hardening_enabled`). |
| `hardening.read_write_paths` | `[]` | Extra writable paths. |
| `logrotate.*` | daily, 14 rotations, 100M | `enabled`, `frequency`, `rotate`, `max_size`, `compress`, `delay_compress`, `missing_ok`, `not_if_empty`. Read from the primary component. |
| `build_commands` | `[]` | Shell commands run once per release as the application account, after `uv sync`. |
| `build_chdir` | `""` | Directory they run in, relative to the release. |
| `build_node` | `false` | Install Node.js on the host. |

### Type specific

| Key | Default | Description |
| --- | --- | --- |
| `gunicorn.workers` | `2` | Worker processes. |
| `gunicorn.socket` | `true` | Listen on `/run/<name>/<name>.sock` instead of `host:port`. |
| `gunicorn.host`, `gunicorn.port` | `127.0.0.1`, `8000` | Listen address when `socket` is `false`. |
| `gunicorn.module` | `<module>.main:app` | ASGI application. |
| `gunicorn.worker_class` | `uvicorn.workers.UvicornWorker` | Worker class. |
| `celery.app` | `<module>.celery:celery_app` | Celery application. |
| `celery.loglevel`, `celery.concurrency` | `info`, `2` | Worker settings. |
| `celery.queues` | `[]` | Queues consumed by a worker. |
| `celery.scheduler` | `""` | Beat scheduler class. |
| `daemon.module`, `daemon.args` | `<module>.main`, `""` | `python -m` target and arguments. |
| `daemon.stop_timeout` | `30` | Seconds before the process is killed. |
| `audiosocket.module`, `audiosocket.host`, `audiosocket.port` | `<module>.main`, `127.0.0.1`, `9092` | AudioSocket server. |
| `fastagi.module`, `fastagi.host`, `fastagi.port`, `fastagi.agi_script` | `<module>.main`, `127.0.0.1`, `4573`, `bot` | FastAGI server and the script name the dialplan requests. |
| `asterisk.enabled` | `false` | Install a dialplan context for an `audiosocket` or `fastagi` component. |
| `asterisk.context`, `asterisk.test_extension` | `fastagi-bot`, `""` | Context name and an optional direct extension for tests. |
| `script.wrappers` | `[]` | Wrapper scripts of a `script` component: `name`, `entrypoint` (relative to `apps/<package>`) and `args`. |
| `openvpn` | `{}` | OpenVPN hooks of a `script` component: `hook_connect`, `hook_disconnect`, `hook_reneg` (wrapper names), `reneg_sec` (300), `management_port` (7505), `server_conf`. |

### Database

| Key | Default | Description |
| --- | --- | --- |
| `postgres.database` | `""` | Database name. The component gets `DATABASE_URL` when set; the database is created from the primary component's entry. |
| `postgres.shared` | `false` | Several applications share a database owned by a group role named like the database. |
| `postgres.pgvector` | `false` | Enable the `vector` extension. |
| `postgres.async_db` | `false` | Use the `postgresql+asyncpg` driver in `DATABASE_URL`. |
| `alembic.enabled` | `false` | Run `alembic -c apps/<package>/alembic.ini upgrade head` before the unit starts. |
| `pg_backup.*` | enabled, 02:00, 7 days, `custom` | `enabled`, `dir`, `hour`, `minute`, `retention` (days), `format` (`custom`, `plain`, `tar`). Not done for shared databases. |

### Web front

| Key | Default | Description |
| --- | --- | --- |
| `nginx.enabled` | `false` | Publish the component through nginx. |
| `nginx.domain` | `website_hostnames.<app>` | Host name served. |
| `nginx.ssl` | `letsencrypt` | `letsencrypt`, `step-ca` or `false` (plain HTTP). |
| `nginx.ssl_wildcard`, `nginx.ssl_wildcard_domains` | `false`, `[]` | Wildcard certificate (Let's Encrypt, DNS-01). |
| `nginx.ssl_dns_provider` | `manual` | `manual` (the certificate must exist) or `route53`. |
| `nginx.dns_wildcard_cname_target` | `""` | With `route53`, create the wildcard CNAME records pointing to this host. |
| `nginx.redirect_domains` | `[]` | Alternate names redirected (301) to the domain and added to the certificate. Let's Encrypt without wildcard only. |
| `nginx.internal_domain` | `false` | Listen on `website_internal_listen` and `127.0.0.1` and register the name in dnsmasq. |
| `nginx.allowed_hosts` | `[]` | Networks allowed to connect; `website_internal_allowed_hosts` for internal hosts when empty. |
| `nginx.websocket.*` | disabled, `/ws`, `1h` | `enabled`, `path`, `timeout`. |
| `nginx.custom_locations` | `[]` | Extra `location` blocks: `path` and `config`. |
| `nginx.client_max_body_size`, `nginx.csp`, `nginx.headers` | `""`, `""`, `[]` | Upload limit, Content-Security-Policy and extra `add_header` lines. |
| `nginx.static.*` | disabled | Serve a directory of the release: `enabled`, `location`, `alias` (relative to the release), `expires`. |
| `fail2ban.enabled`, `fail2ban.routes` | `false`, `[]` | One jail per route: `path`, `method` (POST), `maxretry` (5), `findtime` (10m), `bantime` (1h). |
| `ses_webhook` | `{}` | SES and SNS wiring: `region`, `topic_prefix` and `endpoint` (required), `identity`, `track_deliveries`, `configuration_set`, `event_types`. |

## Behavior

- Everything runs idempotently: a second run without changes reports no
  change. A unit is restarted only when its release, environment file,
  credentials, gunicorn configuration or unit file changed.
- `uv sync` runs with `--frozen`, so a release is installed exactly as locked in
  `uv.lock`. The packages are installed in editable mode, pointing to the
  release directory, so the virtualenv is shared by the releases of an
  application and re-synced on each new one.
- A branch name in `version` is resolved at every run: a new commit on the
  branch is a new release. Pin a tag or a commit to freeze an application.
- Environment files hold configuration only. Secrets are stored as encrypted
  systemd credentials (`systemd-creds encrypt`), declared in the unit with
  `LoadCredentialEncrypted`, and read by the application from
  `$CREDENTIALS_DIRECTORY`. A secret is re-encrypted when its value changes.
  See [Secrets](../03-secrets.md).
- Migrations run as the application account with the environment file loaded,
  before the unit starts, from the primary component.
- A component with `nginx.enabled` gets a virtual host named after its unit.
  When the certificate is missing, an HTTP-only virtual host answers the ACME
  challenge first. Renewal is left to the `certbot` role (set
  `certbot_reload_service: nginx`).
- Without a `website_domain` the host names are not usable: the role stops when
  a virtual host has no domain.
- Check mode (`--check`) reports what it can, but a first deployment cannot be
  predicted: the checkout, the uv installation and the AWS CLI calls do not run.
- Handlers: nginx is reloaded after a virtual host change and restarted when
  `www-data` joins the group of a socket; dnsmasq, fail2ban and Asterisk are
  reloaded or restarted when their configuration changed; OpenVPN is restarted
  when its hooks changed.

## Tags

| Tag | Scope |
| --- | --- |
| `python_app` | Every task of the role. |

Deploy a subset with `website_apps_limit` rather than with tags.

## Example

Pin an application, add a worker queue and serve the frontend on the bare
domain:

```yaml
- hosts: web
  become: true
  roles:
    - role: goabonga.website.python_app
      vars:
        website_domain: example.com
        website_apps_enabled: [frontend, backend]
        website_apps_overrides:
          backend:
            version: backend-v1.2.0
          backend_worker:
            celery:
              queues: [backend, reports]
        website_secrets:
          backend:
            OPENAI_API_KEY: "{{ vault_openai_api_key }}"
            OAUTH2_CLIENT_SECRET: "{{ vault_backend_oauth2_client_secret }}"
```

## See also

- [Deploying applications](../05-deploying-apps.md)
- [Secrets](../03-secrets.md)
- [Playbooks](../06-playbooks.md)
- [nginx](nginx.md), [certbot](certbot.md), [postgres](postgres.md) and [redis](redis.md)
