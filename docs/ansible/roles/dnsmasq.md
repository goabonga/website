# dnsmasq

Install dnsmasq as a local caching DNS resolver with custom records.

Installs dnsmasq and renders its configuration from variables: listen addresses, upstream servers, local domain, host records, CNAMEs, wildcard addresses, per-domain upstreams and raw extra lines. Taking over resolv.conf and disabling systemd-resolved are opt-in.

## Requirements

- Debian 12 or 13, Ubuntu 22.04 or 24.04.
- Privilege escalation (`become: true`).

## Variables

Every variable is optional and defined in `defaults/main.yml`. The role validates them against `meta/argument_specs.yml` before running.

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `dnsmasq_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `dnsmasq_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages. |
| `dnsmasq_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### Installation and service

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `dnsmasq_packages` | list of str | `["dnsmasq"]` | Packages to install. |
| `dnsmasq_service_name` | str | `"dnsmasq"` | systemd unit name. |
| `dnsmasq_service_state` | str | `"started"` | State of the service after configuration. Choices: `started`, `stopped`. |
| `dnsmasq_service_enabled` | bool | `true` | Enable the service at boot. |
| `dnsmasq_config_file` | path | `"/etc/dnsmasq.conf"` | Path of the configuration file written by the role. |
| `dnsmasq_config_dir` | path | `"/etc/dnsmasq.d"` | Directory of additional configuration files (*.conf) included by the main file. |
| `dnsmasq_hosts_file` | path | `"/etc/dnsmasq.hosts"` | File that holds the host records. |
| `dnsmasq_backup_config` | bool | `false` | Keep a timestamped backup of the configuration file when it changes. |

### Listening and forwarding

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `dnsmasq_listen_addresses` | list of str | `["127.0.0.1"]` | Addresses dnsmasq listens on. |
| `dnsmasq_port` | int | `53` | DNS port. |
| `dnsmasq_bind_interfaces` | bool | `true` | Bind only to the listed addresses instead of the wildcard address. |
| `dnsmasq_no_resolv` | bool | `true` | Do not read upstream servers from resolv.conf. |
| `dnsmasq_upstream_servers` | list of str | `["1.1.1.1", "1.0.0.1"]` | Upstream DNS servers. |
| `dnsmasq_domain_needed` | bool | `true` | Never forward names without a dot. |
| `dnsmasq_bogus_priv` | bool | `true` | Never forward reverse lookups for private ranges. |
| `dnsmasq_domain_servers` | list of dict | `[]` | Forward selected domains to specific servers. |

Keys of each `dnsmasq_domain_servers` item:

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | str | yes | Domain to forward. |
| `server` | str | yes | Upstream server. |

### Local domain and cache

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `dnsmasq_local_domain` | str | `"internal"` | Local domain answered from local data only. Disabled when empty. |
| `dnsmasq_expand_hosts` | bool | `true` | Append the local domain to simple names in host records. |
| `dnsmasq_cache_size` | int | `1000` | Number of cached DNS records. |
| `dnsmasq_log_queries` | bool | `false` | Log every query. |
| `dnsmasq_log_facility` | str | `""` | Log file or syslog facility for dnsmasq messages. The default destination is kept when empty. |

### Records

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `dnsmasq_hosts_file` | path | `"/etc/dnsmasq.hosts"` | File that holds the host records. |
| `dnsmasq_hosts` | list of dict | `[]` | Host (A and AAAA) records. |
| `dnsmasq_cnames` | list of dict | `[]` | CNAME records. |
| `dnsmasq_addresses` | list of dict | `[]` | Answers for a whole domain, for example a wildcard development domain. |
| `dnsmasq_extra_config` | list of str | `[]` | Extra raw configuration lines. |

Keys of each `dnsmasq_hosts` item:

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `ip` | str | yes | IPv4 or IPv6 address. |
| `hostname` | str | yes | Host name; several names may be separated by spaces. |

Keys of each `dnsmasq_cnames` item:

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `alias` | str | yes | Alias name. |
| `target` | str | yes | Target name. |

Keys of each `dnsmasq_addresses` item:

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | str | yes | Domain, matches the domain and all of its subdomains. |
| `ip` | str | yes | Address returned. |

### System integration

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `dnsmasq_manage_default_file` | bool | `true` | Write DNSMASQ_EXCEPT in /etc/default/dnsmasq so the resolvconf integration does not interfere. |
| `dnsmasq_except_interface` | str | `"lo"` | Value of DNSMASQ_EXCEPT. |
| `dnsmasq_disable_systemd_resolved` | bool | `false` | Stop and disable systemd-resolved when it is present. |
| `dnsmasq_manage_resolv_conf` | bool | `false` | Point the resolver configuration file at dnsmasq. |
| `dnsmasq_resolv_conf_file` | path | `"/etc/resolv.conf"` | Resolver configuration file written when dnsmasq_manage_resolv_conf is true. |
| `dnsmasq_resolv_nameservers` | list of str | `["127.0.0.1"]` | Name servers written to resolv.conf. |
| `dnsmasq_resolv_search` | list of str | `[]` | Search domains written to resolv.conf. |

## Behavior

- The configuration is validated with `dnsmasq --test` before it replaces the current file.
- By default dnsmasq listens on the loopback address only and nothing else on the host is touched: `/etc/resolv.conf` and systemd-resolved are left alone.
- `dnsmasq_manage_resolv_conf` rewrites the resolver file. Pair it with `dnsmasq_disable_systemd_resolved` when systemd-resolved owns the stub listener, otherwise both services compete for port 53.
- Host records go to a separate hosts file (`dnsmasq_hosts_file`) that dnsmasq reads with `addn-hosts`.
- Files ending in `.conf` in `dnsmasq_config_dir` are included, so other roles can add their own records without editing the main file.
- `dnsmasq_manage_default_file` keeps the Debian resolvconf integration from rewriting the configuration at boot.

## Tags

| Tag | Scope |
| --- | --- |
| `dnsmasq` | Every task of the role. |

## Example

```yaml
- hosts: dns
  become: true
  roles:
    - role: goabonga.website.dnsmasq
      vars:
        dnsmasq_local_domain: internal
        dnsmasq_hosts:
          - {ip: 10.0.0.5, hostname: app}
        dnsmasq_cnames:
          - {alias: www.internal, target: app.internal}
        dnsmasq_manage_resolv_conf: true
        dnsmasq_disable_systemd_resolved: true
```
