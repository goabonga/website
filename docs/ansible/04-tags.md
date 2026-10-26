# Tags

Every role tags its tasks with its own name, so a run can be limited to one
part of the infrastructure. The `python_app` role has a single tag; restrict
it to some applications with a variable instead.

```bash
# Only nginx and certbot
ansible-playbook goabonga.website.site --tags nginx,certbot

# Everything but the firewall
ansible-playbook goabonga.website.bootstrap --skip-tags security_firewall

# Only one application
ansible-playbook goabonga.website.apps -e '{"website_apps_limit": ["backend"]}'

# List the tasks a selection would run
ansible-playbook goabonga.website.site --tags postgres --list-tasks
```

## Tags by role

| Role | Tags |
| --- | --- |
| `users` | `users` |
| `security` | `security`, `security_ssh`, `security_firewall`, `security_unattended_upgrades` |
| `common` | `common`, `common_packages`, `common_system`, `common_bash_prompt`, `common_tmux` |
| `dnsmasq` | `dnsmasq` |
| `redis` | `redis` |
| `postgres` | `postgres` |
| `step_ca` | `step_ca` |
| `step_ca_client` | `step_ca_client` |
| `geoip` | `geoip` |
| `certbot` | `certbot` |
| `nginx` | `nginx` |
| `fail2ban` | `fail2ban` |
| `openvpn` | `openvpn` |
| `openvpn_client` | `openvpn_client` |
| `asterisk` | `asterisk` |
| `protonmail_bridge` | `protonmail_bridge` |
| `python_app` | `python_app` |

The `security` role also tags its three parts, and `common` its four, so one
of them can be run alone: `--tags security_ssh`, `--tags common_tmux`.

## Always-run checks

The check that stops `bootstrap` when SSH would be hardened without a key
carries the `always` tag, so it runs even when a tag selection excludes it.

## Tags and the other switches

A tag selects tasks; a variable switches behavior. They combine:

| To | Use |
| --- | --- |
| Skip a role for every run | `site_<role>: false` (or `bootstrap_<role>: false`) in the inventory |
| Skip a role for one run | `--skip-tags <role>` |
| Run one role only | `--tags <role>` |
| Deploy some applications only | `website_apps_limit` |
| Make a role do nothing | its `<role>_enabled: false` master toggle |

Tags only filter what the playbook would run: a role skipped by its
`site_<role>` switch stays skipped even when its tag is selected.

## Dependencies when limiting a run

Limiting a run does not install what a role needs. `--tags python_app` on a
fresh host fails if PostgreSQL, nginx or certbot are missing and a component
needs them; the role stops with a message that names the missing role.
