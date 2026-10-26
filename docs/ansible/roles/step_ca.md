# step_ca

Installs [step-ca](https://smallstep.com/docs/step-ca) and `step-cli` from the
Smallstep repository and runs a private certificate authority. The role
initialises the CA, keeps selected parts of `ca.json` under Ansible control,
manages ACME and JWK provisioners, can store the CA state in PostgreSQL, serve a
CRL, publish the CA behind a local nginx proxy and distributes the root
certificate to the host trust store and to the controller.

## Requirements

- A Debian-family target (the role asserts `os_family == Debian`).
- A CA password, kept in a vault. Without `step_ca_password` the role installs
  and prepares the host but neither initialises nor starts the CA.
- For PostgreSQL storage: PostgreSQL installed (for example by the `postgres`
  role) and the `community.postgresql` collection on the controller, which
  `goabonga.website` already depends on. The target needs the Python PostgreSQL
  driver used by those modules.
- For the nginx proxy: nginx and certbot installed (the role asserts it).

## Usage

A CA on the loopback interface with an ACME provisioner (the defaults):

```yaml
- hosts: pki
  become: true
  roles:
    - role: goabonga.website.step_ca
      vars:
        step_ca_name: Example Internal CA
        step_ca_password: "{{ vault_step_ca_password }}"
```

PostgreSQL storage, a CRL and an extra provisioner for a service that requests
certificates with a JWK token:

```yaml
- hosts: pki
  become: true
  roles:
    - role: goabonga.website.step_ca
      vars:
        step_ca_password: "{{ vault_step_ca_password }}"
        step_ca_postgres_enabled: true
        step_ca_crl_enabled: true
        step_ca_provisioners:
          - name: openvpn
            password: "{{ vault_openvpn_stepca_password }}"
            max_duration: 8760h
            default_duration: 8760h
```

Run it alone with `--tags step_ca`.

## What it does

1. Validates the target and the provisioner definitions.
2. Adds the Smallstep apt repository and installs `step-cli` and `step-ca`.
3. Creates the `step` user and group and the directories under
   `/etc/step-ca` (`config`, `certs`, `secrets`), then writes the CA password
   file (mode `0600`).
4. Runs `step ca init` once, with the names of `step_ca_dns_names`. It is skipped
   when `config/ca.json` exists. The public certificates get
   `step_ca_public_certs_mode`.
5. With `step_ca_postgres_enabled`: asserts PostgreSQL is installed, creates the
   database role and database, grants the privileges and adds the CA user to the
   `postgres` group so it can use the Unix socket.
6. Reads `ca.json` and rewrites it only if a managed value differs: `address`,
   `dnsNames`, the `db` section (PostgreSQL, or back to BadgerDB when PostgreSQL
   was disabled) and the CRL settings (`insecureAddress` and `crl`, removed when
   `step_ca_crl_enabled` is false).
7. Creates the ACME provisioner, the VPN portal provisioner and the entries of
   `step_ca_provisioners`, or updates their certificate durations and renewal
   flag when they differ.
8. Installs the systemd unit, starts the CA and waits for the port.
9. Copies the root certificate to the system trust store and fetches it to
   `step_ca_export_dir` on the controller.
10. With `step_ca_nginx_enabled`: adds a dnsmasq entry for the domain (when
    dnsmasq is installed), requests a certificate from the CA itself through
    certbot and ACME, then publishes a TLS reverse proxy.

Everything is idempotent: the commands that change the CA only run when the
state read from `ca.json` shows a difference.

## Behaviour to know about

- `ca.json` is parsed and written back as indented JSON. Only the keys listed
  above are touched, but `step_ca_dns_names` is authoritative: names removed
  from the list disappear from the file. Include every name or address clients
  use to reach the CA, in particular `127.0.0.1` for the local certbot request.
- Provisioner durations are compared as strings with what `ca.json` contains. If
  the CLI stores a duration in another notation than the one you set, the role
  reports a change on each run.
- The VPN portal provisioner is a short-lived JWK provisioner (15 minutes
  maximum by default, renewal disabled). Its password file is group-readable
  (`0640`) so an application user added to the `step` group can sign tokens, and
  its public key is saved in the secrets directory and fetched to the
  controller.
- The nginx proxy does not verify the loopback connection to the CA
  (`proxy_ssl_verify off`), as the CA only listens on the local interface.
  certbot verifies the CA with its root certificate unless
  `step_ca_certbot_verify_tls` is false.
- The certbot renewal timer needs to trust the CA: keep `step_ca_trust_system`
  enabled on the host.

## PostgreSQL storage with the postgres role

The role creates the database objects but does not edit PostgreSQL
authentication files. With the `postgres` role, allow the CA user through a
`peer` map:

```yaml
postgres_ident_maps:
  - { map: step-ca-map, system_user: step, pg_user: step_ca }
postgres_hba_extra_rules:
  - { type: local, database: step_ca, user: step_ca, method: peer, options: "map=step-ca-map" }
```

## Variables

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `step_ca_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages. |
| `step_ca_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### Installation

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_manage_repository` | bool | `true` | Configure the Smallstep apt repository. Disable it when the packages come from elsewhere. |
| `step_ca_repository_name` | str | `"smallstep"` | Name of the deb822 repository file. |
| `step_ca_repository_uri` | str | `"https://packages.smallstep.com/stable/debian"` | Repository URI. |
| `step_ca_repository_suite` | str | `"debs"` | Repository suite. |
| `step_ca_repository_component` | str | `"main"` | Repository component. |
| `step_ca_repository_key_url` | str | `"https://packages.smallstep.com/keys/apt/repo-signing-key.gpg"` | URL of the repository signing key. |
| `step_ca_repository_key_path` | path | `"/etc/apt/keyrings/smallstep.asc"` | Where the signing key is stored. |
| `step_ca_prerequisite_packages` | list | `[ca-certificates]` | Packages needed before the repository can be used. |
| `step_ca_packages` | list | `[step-cli, step-ca]` | Packages to install. |

### Certificate authority

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_name` | str | `"Internal CA"` | Name of the certificate authority. |
| `step_ca_password` | str | `""` | Password protecting the CA keys and the initial provisioner. Provide it from a vault. When empty the role installs and prepares everything but neither initialises nor starts the CA. |
| `step_ca_provisioner` | str | `"admin"` | Name of the initial JWK provisioner created with the CA. |
| `step_ca_dns_names` | list | `['{{ ansible_facts[''fqdn''] }}', localhost, 127.0.0.1, '{{ step_ca_domain }}']` | DNS names and IP addresses the CA certificate is valid for. They are written to ca.json and the list is authoritative. |
| `step_ca_listen_address` | str | `"127.0.0.1"` | Address the CA listens on. |
| `step_ca_port` | int | `8443` | Port the CA listens on. |
| `step_ca_address` | str | `"{{ step_ca_listen_address }}:{{ step_ca_port }}"` | Listen address as written to ca.json. |
| `step_ca_url` | str | `"https://{{ '127.0.0.1' if step_ca_listen_address in ['0.0.0.0', '::'] else step_ca_listen_address }}:{{ step_ca_port }}"` | URL local clients use to reach the CA. |
| `step_ca_domain` | str | `"step-ca.internal"` | Internal name of the CA, used by the nginx proxy and the DNS entry. |

### Account and paths

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_user` | str | `"step"` | System user running the CA. |
| `step_ca_group` | str | `"step"` | Group of the CA user. |
| `step_ca_home` | path | `"/etc/step-ca"` | STEPPATH of the CA. |
| `step_ca_config_dir` | path | `"{{ step_ca_home }}/config"` | Directory holding ca.json. |
| `step_ca_certs_dir` | path | `"{{ step_ca_home }}/certs"` | Directory holding the root and intermediate certificates. |
| `step_ca_secrets_dir` | path | `"{{ step_ca_home }}/secrets"` | Directory holding the keys and password files. |
| `step_ca_secrets_dir_mode` | str | `"0750"` | Mode of the secrets directory. The group may traverse it so that application users added to the group can read the files they own. |
| `step_ca_public_certs_mode` | str | `"0644"` | Mode of root_ca.crt and intermediate_ca.crt. |
| `step_ca_binary` | path | `"/usr/bin/step-ca"` | Path of the step-ca executable. |

### Service

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_service_name` | str | `"step-ca"` | systemd unit name. |
| `step_ca_service_state` | str | `"started"` | State of the service after configuration. |
| `step_ca_service_enabled` | bool | `true` | Enable the service at boot. |
| `step_ca_service_hardening` | bool | `true` | Add sandboxing options (NoNewPrivileges, ProtectSystem, ProtectHome, PrivateTmp) to the unit. |
| `step_ca_restart_sec` | int | `5` | RestartSec= of the unit. |
| `step_ca_wait_for_ready` | bool | `true` | Wait until the CA accepts connections before finishing. |
| `step_ca_wait_timeout` | int | `30` | Seconds to wait for readiness. |

### ACME provisioner

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_acme_enabled` | bool | `true` | Create the ACME provisioner, for example for certbot. |
| `step_ca_acme_provisioner` | str | `"acme"` | Name of the ACME provisioner. |
| `step_ca_acme_max_duration` | str | `"8760h"` | Maximum certificate duration of the ACME provisioner. |
| `step_ca_acme_default_duration` | str | `"720h"` | Default certificate duration of the ACME provisioner. |

### Additional provisioners

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_provisioners` | list | `[]` | Extra provisioners to create. JWK provisioners are created with a generated key protected by the given password. |
| `step_ca_vpn_portal_enabled` | bool | `false` | Create the JWK provisioner of the VPN portal, issuing short-lived certificates, and export its public key. |
| `step_ca_vpn_portal_provisioner` | str | `"vpn-portal"` | Name of the VPN portal provisioner. |
| `step_ca_vpn_portal_password` | str | `""` | Password of the VPN portal provisioner key. Required when it is enabled. Provide it from a vault. |
| `step_ca_vpn_portal_max_duration` | str | `"15m"` | Maximum certificate duration of the VPN portal provisioner. |
| `step_ca_vpn_portal_default_duration` | str | `"10m"` | Default certificate duration of the VPN portal provisioner. |
| `step_ca_vpn_portal_disable_renewal` | bool | `true` | Forbid renewal of the short-lived certificates. |

### PostgreSQL storage

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_postgres_enabled` | bool | `false` | Store certificates and revocations in PostgreSQL instead of the embedded BadgerDB. PostgreSQL must be installed and reachable first. |
| `step_ca_postgres_manage_objects` | bool | `true` | Create the database role and the database. |
| `step_ca_postgres_binary` | path | `"/usr/bin/psql"` | Path of psql, used to check that PostgreSQL is installed. |
| `step_ca_postgres_admin_user` | str | `"postgres"` | System user the PostgreSQL modules run as. |
| `step_ca_postgres_group` | str | `"postgres"` | Group the CA user joins to reach the Unix socket. Empty skips the membership. |
| `step_ca_postgres_database` | str | `"step_ca"` | Database name. |
| `step_ca_postgres_user` | str | `"step_ca"` | Database role used by the CA. |
| `step_ca_postgres_password` | str | `""` | Password of the database role. Empty relies on peer authentication over the Unix socket. |
| `step_ca_postgres_socket_dir` | path | `"/var/run/postgresql"` | Directory of the PostgreSQL Unix socket. |

### Certificate revocation list

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_crl_enabled` | bool | `false` | Serve a CRL over the insecure HTTP address of the CA. When false the CRL settings are removed from ca.json. |
| `step_ca_crl_listen_address` | str | `"127.0.0.1"` | Address of the insecure HTTP listener. |
| `step_ca_crl_port` | int | `9001` | Port of the insecure HTTP listener. |
| `step_ca_crl_address` | str | `"{{ step_ca_crl_listen_address }}:{{ step_ca_crl_port }}"` | Insecure address as written to ca.json. |
| `step_ca_crl_url` | str | `"http://{{ step_ca_crl_address }}/1.0/crl"` | CRL distribution point. |

### Trust and export

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_trust_system` | bool | `true` | Add the root certificate to the system trust store. |
| `step_ca_trust_ca_path` | path | `"/usr/local/share/ca-certificates/step-ca-root.crt"` | Where the root certificate is copied for update-ca-certificates. |
| `step_ca_export_enabled` | bool | `true` | Fetch the root certificate (and the VPN portal public key) to the controller. |
| `step_ca_export_dir` | path | `"{{ playbook_dir }}/files/step-ca"` | Controller directory receiving the exported files. |

### DNS entry

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_dnsmasq_enabled` | bool | `true` | Point the CA domain to the loopback address in dnsmasq when it is installed and the nginx proxy is enabled. |
| `step_ca_dnsmasq_binary` | path | `"/usr/sbin/dnsmasq"` | Path of dnsmasq, used to detect an installation. |
| `step_ca_dnsmasq_hosts_file` | path | `"/etc/dnsmasq.d/internal-domains.conf"` | dnsmasq file receiving the address entry. |
| `step_ca_dnsmasq_service_name` | str | `"dnsmasq"` | systemd unit restarted after a change. |

### Nginx proxy

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_nginx_enabled` | bool | `false` | Publish the CA behind nginx under its internal domain, with a certificate obtained from the CA itself through certbot. nginx and certbot must be installed. |
| `step_ca_nginx_binary` | path | `"/usr/sbin/nginx"` | Path of nginx, used to detect an installation. |
| `step_ca_nginx_service_name` | str | `"nginx"` | systemd unit reloaded after a change. |
| `step_ca_nginx_listen_address` | str | `"127.0.0.1"` | Address the proxy listens on. |
| `step_ca_nginx_http_port` | int | `80` | HTTP port of the proxy. |
| `step_ca_nginx_https_port` | int | `443` | HTTPS port of the proxy. |
| `step_ca_nginx_sites_available` | path | `"/etc/nginx/sites-available"` | nginx sites-available directory. |
| `step_ca_nginx_sites_enabled` | path | `"/etc/nginx/sites-enabled"` | nginx sites-enabled directory. |
| `step_ca_nginx_webroot` | path | `"/var/www/html"` | Webroot used for the ACME HTTP challenge. |
| `step_ca_nginx_ssl_protocols` | str | `"TLSv1.2 TLSv1.3"` | ssl_protocols of the proxy. |
| `step_ca_nginx_ssl_ciphers` | str | `"ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384"` | ssl_ciphers of the proxy. |
| `step_ca_certbot_binary` | path | `"/usr/bin/certbot"` | Path of certbot, used to detect an installation. |
| `step_ca_certbot_email` | str | `""` | Contact e-mail for the certificate. Empty registers without an e-mail address. |
| `step_ca_certbot_verify_tls` | bool | `true` | Verify the TLS certificate of the CA when certbot connects to it, using the root certificate. Disabling it adds --no-verify-ssl. |
| `step_ca_letsencrypt_live_dir` | path | `"/etc/letsencrypt/live"` | Directory holding the certbot certificates. |


## Handlers

| Topic | Effect |
| --- | --- |
| `step_ca \| reload systemd` | Runs `systemctl daemon-reload`. |
| `step_ca \| restart` | Restarts the CA (only when the service state is `started`, a password is set and the CA is initialised). |
| `step_ca \| update ca certificates` | Runs `update-ca-certificates`. |
| `step_ca \| reload nginx` | Reloads the nginx unit. |
| `step_ca \| restart dnsmasq` | Restarts the dnsmasq unit. |

## Verification status

The role is checked with `ansible-playbook --syntax-check`, the argument
specification is validated against the defaults, the templates are rendered
locally, and the `ca.json` merge logic and the provisioner command lines were
evaluated against a sample `ca.json`. It has not been run against a live host:
the repository setup, `step ca init`, the `step ca provisioner add/update`
flags (including `--disable-renewal` and `--deployment-type`), the PostgreSQL
tasks, the ACME bootstrap through certbot and the nginx publication are
untested.
