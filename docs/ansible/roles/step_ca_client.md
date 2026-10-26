# step_ca_client

Prepares a host to use a private [step-ca](step_ca.md) authority: it installs
the root certificate in the system trust store and configures certbot to request
certificates from the authority's ACME directory.

## Requirements

- A Debian-family or Arch Linux target (the role asserts it).
- The root certificate of the authority on the controller. The
  [step_ca](step_ca.md) role fetches it to `files/step-ca/root_ca.crt` next to
  the playbook, which is the default of `step_ca_client_root_cert`. The role
  stops with an explicit message when the file is missing.
- For Arch Linux, the `community.general` collection (a dependency of
  `goabonga.website`).
- Network access from the host to the ACME URL, usually through a VPN.

## Usage

```yaml
- hosts: workstations
  become: true
  roles:
    - role: goabonga.website.step_ca_client
      vars:
        step_ca_client_acme_url: https://step-ca.internal/acme/acme/directory
```

Trust the root certificate only, without certbot:

```yaml
- hosts: workstations
  become: true
  roles:
    - role: goabonga.website.step_ca_client
      vars:
        step_ca_client_install_certbot: false
```

Once the role has run, request a certificate with
`certbot certonly --webroot -w /var/www/html -d host.internal`: the server,
terms agreement and contact settings come from `cli.ini`.

Run it alone with `--tags step_ca_client`.

## What it does

1. Validates the target and checks that the root certificate exists on the
   controller.
2. Stores the root certificate at `step_ca_client_root_cert_dest` and, when
   `step_ca_client_trust_system` is true, adds it to the trust store
   (`update-ca-certificates` on Debian, `update-ca-trust` on Arch Linux).
3. With `step_ca_client_install_certbot`: installs certbot, writes
   `<certbot config dir>/cli.ini` with the ACME directory, and installs a
   deploy hook that reloads `step_ca_client_deploy_hook_services` after each
   renewal (removed when `step_ca_client_deploy_hook_enabled` is false).

## Variables

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_client_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `step_ca_client_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages (Debian family). |
| `step_ca_client_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### Root certificate

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_client_root_cert` | path | `"{{ playbook_dir }}/files/step-ca/root_ca.crt"` | Root certificate on the controller. The step_ca role fetches it there by default. |
| `step_ca_client_root_cert_dest` | path | `"/etc/step-ca/certs/root_ca.crt"` | Where the root certificate is stored on the host. |

### System trust store

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_client_trust_system` | bool | `true` | Add the root certificate to the system trust store. |
| `step_ca_client_trust_path_debian` | path | `"/usr/local/share/ca-certificates/step-ca-root.crt"` | Trust anchor path on Debian-family hosts (update-ca-certificates). |
| `step_ca_client_trust_path_archlinux` | path | `"/etc/ca-certificates/trust-source/anchors/step-ca-root.crt"` | Trust anchor path on Arch Linux (update-ca-trust). |

### Certbot

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `step_ca_client_install_certbot` | bool | `true` | Install certbot and configure it for the authority. |
| `step_ca_client_certbot_package` | str | `"certbot"` | Package providing certbot. |
| `step_ca_client_acme_url` | str | `"https://step-ca.internal/acme/acme/directory"` | ACME directory URL of the authority. |
| `step_ca_client_certbot_email` | str | `""` | Contact e-mail written to cli.ini. Empty registers without an e-mail address. |
| `step_ca_client_certbot_config_dir` | path | `"/etc/letsencrypt"` | certbot configuration directory. |
| `step_ca_client_deploy_hook_enabled` | bool | `true` | Install a deploy hook reloading services after a renewal. When false the hook is removed. |
| `step_ca_client_deploy_hook_name` | str | `"reload-services.sh"` | File name of the deploy hook in renewal-hooks/deploy. |
| `step_ca_client_deploy_hook_services` | list | `[nginx]` | Services reloaded by the deploy hook. A service that is not running is ignored. |


## Handlers

| Topic | Effect |
| --- | --- |
| `step_ca_client \| update ca certificates` | Runs `update-ca-certificates` (Debian family). |
| `step_ca_client \| update ca trust` | Runs `update-ca-trust` (Arch Linux). |

## Verification status

The role is checked with `ansible-playbook --syntax-check`, the argument
specification is validated against the defaults, the templates are rendered
locally and the failure path for a missing root certificate was exercised. It
has not been run against a live host: package installation, the trust store
update and a certificate request against a real authority are untested.
