# postgres

Installs PostgreSQL from the distribution packages and renders its three
configuration files from variables. It can also create roles and databases and
enable the pgvector extension.

## Requirements

- A Debian-family target (the role asserts `os_family == Debian`).
- The `community.postgresql` collection on the controller (already a
  dependency of `goabonga.website`).
- `python3-psycopg2` on the target; it is part of `postgres_packages`.

## Usage

```yaml
- hosts: databases
  become: true
  roles:
    - role: goabonga.website.postgres
      vars:
        postgres_version: "17"
        postgres_port: 0                 # Unix socket only
        postgres_pgvector_enabled: true
        postgres_users:
          - name: app
        postgres_databases:
          - name: app
            owner: app
            extensions: [vector]
```

Run it alone with `--tags postgres`.

## What it does

1. Installs the server, client and `python3-psycopg2` packages (plus the
   optional extra packages and the pgvector package).
2. Renders `postgresql.conf`, `pg_hba.conf` and `pg_ident.conf` into
   `postgres_config_dir`. A change to `postgresql.conf` restarts the service, a
   change to the other two reloads it.
3. Starts and enables the service.
4. Creates the roles in `postgres_users`, the databases in `postgres_databases`
   and enables the extensions listed on each database.

Setting `postgres_enabled: false` skips every task.

## Authentication model

The default is peer authentication on the Unix socket: an operating system user
connects as the PostgreSQL role of the same name, with no password. That is what
the applications of this repository rely on. A role named after the service user
(for example `app`) plus a database owned by it is enough.

When a different mapping is required, declare it in `postgres_ident_maps` and
reference it from a rule in `postgres_hba_extra_rules` with
`options: map=<name>`. When TCP is enabled, `postgres_hba_extra_rules` is also
where remote clients are allowed.

Role passwords are passed through `no_log` tasks. Provide them from a vault
variable, never from the inventory in clear text.

## Variables

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `postgres_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `postgres_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages. |
| `postgres_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### Installation

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `postgres_version` | str | `"17"` | Major PostgreSQL version to install (must exist in the distribution repositories). |
| `postgres_packages` | list | `['postgresql-{{ postgres_version }}', 'postgresql-client-{{ postgres_version }}', python3-psycopg2]` | Packages installed for the server. python3-psycopg2 is required by the community.postgresql modules. |
| `postgres_extra_packages` | list | `[]` | Additional packages to install (for example contrib extensions). |
| `postgres_pgvector_enabled` | bool | `false` | Install the pgvector extension package. |
| `postgres_pgvector_package` | str | `"postgresql-{{ postgres_version }}-pgvector"` | Package providing pgvector. |
| `postgres_pgvector_databases` | list | `[]` | Databases in which `CREATE EXTENSION vector` is executed when pgvector is enabled. |

### Paths and service

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `postgres_service_name` | str | `"postgresql"` | systemd unit managing the cluster. |
| `postgres_config_dir` | path | `"/etc/postgresql/{{ postgres_version }}/main"` | Directory holding postgresql.conf, pg_hba.conf and pg_ident.conf. |
| `postgres_data_dir` | path | `"/var/lib/postgresql/{{ postgres_version }}/main"` | Cluster data directory. |
| `postgres_service_state` | str | `"started"` | State of the service after configuration. |
| `postgres_service_enabled` | bool | `true` | Enable the service at boot. |

### Connections

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `postgres_port` | int | `5432` | TCP port. Set to 0 to disable TCP and listen on the Unix socket only. |
| `postgres_listen_addresses` | str | `"localhost"` | Value of listen_addresses when TCP is enabled. |
| `postgres_socket_dir` | path | `"/var/run/postgresql"` | Unix socket directory. |
| `postgres_socket_permissions` | str | `"0770"` | Octal permissions of the Unix socket. |
| `postgres_socket_group` | str | `""` | Group owning the Unix socket. Empty keeps the server default. |
| `postgres_max_connections` | int | `100` | Maximum number of concurrent connections. |

### Authentication

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `postgres_local_auth` | str | `"peer"` | Method for local (Unix socket) connections of non-postgres users (peer, md5, scram-sha-256, trust). |
| `postgres_host_auth` | str | `"scram-sha-256"` | Method for the loopback TCP entries (only rendered when the port is not 0). |
| `postgres_hba_extra_rules` | list | `[]` | Additional pg_hba.conf lines rendered after the defaults. |
| `postgres_ident_maps` | list | `[]` | Entries of pg_ident.conf for peer or ident maps. |

### Tuning

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `postgres_shared_buffers` | str | `"128MB"` | shared_buffers. |
| `postgres_work_mem` | str | `"4MB"` | work_mem. |
| `postgres_maintenance_work_mem` | str | `"64MB"` | maintenance_work_mem. |
| `postgres_effective_cache_size` | str | `"4GB"` | effective_cache_size. |
| `postgres_wal_level` | str | `"replica"` | wal_level. |
| `postgres_max_wal_size` | str | `"1GB"` | max_wal_size. |
| `postgres_min_wal_size` | str | `"80MB"` | min_wal_size. |
| `postgres_extra_settings` | dict | `{}` | Additional postgresql.conf settings as a name/value mapping, appended verbatim (strings are quoted). |

### Logging and locale

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `postgres_log_rotation_age` | str | `"1d"` | log_rotation_age. |
| `postgres_log_rotation_size` | str | `"10MB"` | log_rotation_size. |
| `postgres_log_line_prefix` | str | `"%m [%p] %q%u@%d "` | log_line_prefix. |
| `postgres_timezone` | str | `"UTC"` | timezone and log_timezone. |
| `postgres_locale` | str | `"en_US.UTF-8"` | Value for lc_messages, lc_monetary, lc_numeric and lc_time. |
| `postgres_text_search_config` | str | `"pg_catalog.english"` | default_text_search_config. |

### Roles and databases

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `postgres_users` | list | `[]` | PostgreSQL roles to create. |
| `postgres_databases` | list | `[]` | Databases to create. |


## Handlers

| Topic | Effect |
| --- | --- |
| `postgres \| restart` | Restarts the service. |
| `postgres \| reload` | Reloads the configuration. |

Handlers are flushed at the end of the configuration step, before roles and
databases are created.

## Verification status

The role is checked with `ansible-playbook --syntax-check`, the argument
specification is validated against the defaults and the templates are rendered
locally. It has not been run against a live host.
