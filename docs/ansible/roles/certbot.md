# certbot

Install certbot, automate renewal and issue Let's Encrypt certificates.

Installs certbot, keeps the renewal timer running, installs renewal hooks and obtains the certificates described in certbot_certificates. Certificates are issued only when they do not exist yet, so the role is idempotent.

## Requirements

- Debian 12 or 13, Ubuntu 22.04 or 24.04.
- Privilege escalation (`become: true`).
- A reachable web server (webroot method) or free port 80 (standalone method) when certificates are requested.

## Variables

Every variable is optional and defined in `defaults/main.yml`. The role validates them against `meta/argument_specs.yml` before running.

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `certbot_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `certbot_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages. |
| `certbot_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### Installation

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `certbot_packages` | list of str | `["certbot"]` | Packages installed for certbot. |
| `certbot_plugin_packages` | list of str | `[]` | Extra plugin packages, for example python3-certbot-nginx or python3-certbot-dns-cloudflare. |
| `certbot_letsencrypt_dir` | path | `"/etc/letsencrypt"` | Certbot configuration directory. |

### Account and authority

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `certbot_email` | str | `""` | Account e-mail address. Required when certbot_certificates is not empty. |
| `certbot_agree_tos` | bool | `false` | Accept the certificate authority terms of service. Must be true to issue certificates. |
| `certbot_staging` | bool | `false` | Use the staging environment of the certificate authority. |
| `certbot_server` | str | `""` | Custom ACME directory URL. The Let's Encrypt production server is used when empty. |
| `certbot_key_type` | str | `""` | Key type of new certificates. The certbot default is used when empty. Choices: ``, `rsa`, `ecdsa`. |

### Certificates

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `certbot_default_method` | str | `"webroot"` | Authentication method used by certificates that do not set one. Choices: `webroot`, `standalone`, `nginx`, `apache`. |
| `certbot_webroot` | path | `"/var/www/html"` | Web root served at /.well-known/acme-challenge/ for the webroot method. Must match the web server configuration. |
| `certbot_certificates` | list of dict | `[]` | Certificates to obtain. |

Keys of each `certbot_certificates` item:

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `domains` | list of str | yes | Domain names, the first one names the certificate by default. |
| `name` | str | no | Certificate name, also the directory under /etc/letsencrypt/live. |
| `method` | str | no | Authentication method. Choices: `webroot`, `standalone`, `nginx`, `apache`. |
| `webroot` | path | no | Web root for this certificate. |
| `email` | str | no | Account e-mail for this certificate. |
| `key_type` | str | no | Key type. Choices: `rsa`, `ecdsa`. |
| `extra_args` | list of str | no | Additional certbot command line arguments. |

### Renewal

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `certbot_auto_renew` | bool | `true` | Enable and start the systemd renewal timer. The timer is stopped and disabled when false. |
| `certbot_timer` | str | `"certbot.timer"` | Name of the renewal timer unit. |
| `certbot_reload_service` | str | `""` | Service reloaded after each renewal, for example nginx. No reload hook is installed when empty. |
| `certbot_hooks` | list of dict | `[]` | Additional renewal hooks. |

Keys of each `certbot_hooks` item:

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | str | yes | Hook file name without extension. |
| `type` | str | yes | When the hook runs. Choices: `pre`, `deploy`, `post`. |
| `command` | str | yes | Shell command to run. |

## Behavior

- A certificate is requested only when `live/<name>/fullchain.pem` does not exist, so re-running the role never asks the authority again. Renewals are left to the systemd timer.
- The certificate name defaults to its first domain. Domain lists are passed as `--domain` options.
- The role stops before any change when a requested certificate lacks `certbot_agree_tos: true` or an e-mail address.
- With the webroot method, the web server must serve `certbot_webroot` at `/.well-known/acme-challenge/` before the role runs; the `nginx` role does so for its host name virtual host.
- `certbot_reload_service` installs a deploy hook that reloads the service after each renewal. Leave it empty to install no hook; an existing hook of the role is removed.
- Custom hooks are written to `renewal-hooks/<type>/<name>.sh` as small shell scripts.
- Use `certbot_staging: true` while testing to stay clear of the production rate limits.

## Tags

| Tag | Scope |
| --- | --- |
| `certbot` | Every task of the role. |

## Example

```yaml
- hosts: web
  become: true
  roles:
    - role: goabonga.website.certbot
      vars:
        certbot_email: ops@example.com
        certbot_agree_tos: true
        certbot_reload_service: nginx
        certbot_certificates:
          - domains: [example.com, www.example.com]
```

## See also

- `nginx` role: serves the ACME challenge directory and can obtain the certificate of its host name by itself.
