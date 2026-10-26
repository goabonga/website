# Playbooks

The collection ships three playbooks in its `playbooks/` directory. Run them by
their fully qualified name:

```bash
ansible-playbook goabonga.website.bootstrap -e ansible_user=root
ansible-playbook goabonga.website.site
ansible-playbook goabonga.website.apps
```

They are meant to be run in this order, and each can be re-run at any time.

| Playbook | When | As | Roles |
| --- | --- | --- | --- |
| `bootstrap` | Once per host | The account the provider created | `users`, `security` |
| `site` | Whenever the infrastructure changes | The deploy account | The base infrastructure roles |
| `apps` | On every deployment | The deploy account | `python_app` |

All three:

- target `website_hosts` (`all` by default): `-e website_hosts=web` limits a run
  to a group or a host, as `--limit` does;
- gather facts and escalate privileges;
- carry a `website_playbook_version` variable, the version of the playbook.

## bootstrap

Creates the deploy account (`users`) and hardens SSH (`security`). It runs with
the account the hosting provider created, usually `root`, because the deploy
account does not exist yet.

```bash
ansible-playbook goabonga.website.bootstrap -e ansible_user=root
```

Before touching the host it checks that SSH is not hardened without a way in:
if the deploy account is created, `users_deploy_ssh_public_keys` must contain at
least one key, unless password logins stay allowed
(`security_ssh_password_authentication: true`) or the SSH hardening is off
(`security_ssh_enabled: false`).

| Switch | Default | Effect |
| --- | --- | --- |
| `bootstrap_users` | `true` | Run the `users` role. |
| `bootstrap_security` | `true` | Run the `security` role. |

The variables of the two roles are on their pages: [users](roles/users.md) and
[security](roles/security.md).

## site

Provisions the base infrastructure, in this order. Each role runs only when its
`site_<role>` switch is true:

| Order | Role | Switch | Default |
| --- | --- | --- | --- |
| 1 | [common](roles/common.md) | `site_common` | on |
| 2 | [users](roles/users.md) | `site_users` | off |
| 3 | [security](roles/security.md) | `site_security` | off |
| 4 | [dnsmasq](roles/dnsmasq.md) | `site_dnsmasq` | off |
| 5 | [redis](roles/redis.md) | `site_redis` | on |
| 6 | [postgres](roles/postgres.md) | `site_postgres` | on |
| 7 | [step_ca](roles/step_ca.md) | `site_step_ca` | off |
| 8 | [step_ca_client](roles/step_ca_client.md) | `site_step_ca_client` | off |
| 9 | [geoip](roles/geoip.md) | `site_geoip` | off |
| 10 | [certbot](roles/certbot.md) | `site_certbot` | on |
| 11 | [nginx](roles/nginx.md) | `site_nginx` | on |
| 12 | [fail2ban](roles/fail2ban.md) | `site_fail2ban` | on |
| 13 | [openvpn](roles/openvpn.md) | `site_openvpn` | off |
| 14 | [openvpn_client](roles/openvpn_client.md) | `site_openvpn_client` | off |
| 15 | [asterisk](roles/asterisk.md) | `site_asterisk` | off |
| 16 | [protonmail_bridge](roles/protonmail_bridge.md) | `site_protonmail_bridge` | off |

The roles that every web host needs are on. The ones tied to a role of the
host (the private CA, the VPN, telephony, the mail bridge) are off: turn them on
for the group of hosts that has that role, in `inventory/group_vars/<group>.yml`:

```yaml
# inventory/group_vars/internal_ca.yml
site_step_ca: true
site_dnsmasq: true
step_ca_password: "{{ vault_step_ca_password }}"
```

`users` and `security` are off because `bootstrap` runs them; turn them on to
manage the accounts and SSH hardening from `site` as well.

The order matters: `dnsmasq` resolves the internal names before the private CA
and the certificates need them, `certbot` precedes `nginx` (which requests a
certificate for the host name), and `fail2ban` follows `nginx` so its jails
find the logs.

Each role's own master toggle (`nginx_enabled`, `redis_enabled`, ...) still
applies inside the role.

## apps

Deploys the applications selected by `website_apps_enabled` with the
[python_app](roles/python_app.md) role.

```bash
ansible-playbook goabonga.website.apps
ansible-playbook goabonga.website.apps -e '{"website_apps_limit": ["auth", "backend"]}'
ansible-playbook goabonga.website.apps --check --diff
```

It assumes `site` has run: PostgreSQL, Redis, nginx, certbot and fail2ban are
used by the components that declare them, and the role stops with a message
when one is missing. See [Deploying applications](05-deploying-apps.md).

## Using the playbooks from your own project

Besides running them by name, import them from a playbook of your own to add
plays before or after:

```yaml
# site.yml of your project
- ansible.builtin.import_playbook: goabonga.website.site
- ansible.builtin.import_playbook: goabonga.website.apps

- name: Project specific
  hosts: web
  become: true
  tasks:
    - name: Install a tool
      ansible.builtin.apt:
        name: htop
```

Or call a role directly, with the playbooks as a model:

```yaml
- hosts: web
  become: true
  roles:
    - role: goabonga.website.nginx
```

## Versioning

Each playbook has its own version, in `website_playbook_version`, and the
collection has another (`galaxy.yml`), which versions the roles. Pin the
collection in `requirements.yml` for reproducible runs.
