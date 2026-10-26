# Configuration

Everything is configured with Ansible variables. This page explains where they
live, how they layer and which prefixes mean what.

## Naming

| Prefix | Owner | Example |
| --- | --- | --- |
| `<role>_` | One role. Every setting of a role starts with the role name. | `nginx_hostname`, `postgres_version`, `users_deploy_name` |
| `website_` | The platform: shared by the `python_app` role and the playbooks. | `website_domain`, `website_apps_enabled`, `website_secrets` |
| `site_<role>` | `site.yml`: turns a role on or off. | `site_step_ca: true` |
| `bootstrap_<role>` | `bootstrap.yml`: turns a role on or off. | `bootstrap_security: false` |
| `vault_` | Your vault: a secret value, referenced from other variables. | `vault_openai_api_key` |
| `python_app__`, `<role>__` | Internal to a role. Do not set. | |

A role's variables are listed on its page under [Roles](roles/index.md) and
validated against its `argument_specs` before it runs, so a mistyped value
fails early with a clear message.

## Layers

From the lowest to the highest precedence, the places a variable can be set:

1. **Role defaults** (`defaults/main.yml`, or `defaults/main/` for
   `python_app`): the documented defaults.
2. **Inventory `group_vars/all`**: settings shared by every host. This is where
   most of the configuration lives (`inventory/group_vars/all/main.yml` and
   `apps.yml` in the example).
3. **Inventory `group_vars/<group>`**: settings of a group of hosts, for
   example `site_step_ca: true` for the group of the internal CA host.
4. **Inventory `host_vars/<host>`**: settings of one host.
5. **Play and role `vars`**, then **extra variables** (`-e`): one-off values on
   the command line, for example `-e '{"website_apps_limit": ["auth"]}'`.

Rules of thumb:

- Put a value in the lowest layer where it is true for every host that reads
  it, and override it only where it differs.
- Keep secrets out of the layers above: reference a `vault_` variable instead
  (see [Secrets](03-secrets.md)).
- Use `-e` for things that are true of one run, not of the infrastructure.

## Variables shared between roles

Some roles describe the same resource, and the `python_app` role follows them
instead of asking twice:

| Resource | Set it with | `python_app` reads |
| --- | --- | --- |
| Redis socket | `redis_socket` (redis role) | `website_redis_socket` |
| PostgreSQL socket directory | `postgres_socket_dir` (postgres role) | `website_postgres_socket_dir` |
| OpenVPN server file and unit | `openvpn_config_dir`, `openvpn_server_name` (openvpn role) | `website_openvpn_server_conf`, `website_openvpn_service` |
| Asterisk directory and account | `asterisk_config_dir`, `asterisk_user`, `asterisk_group` (asterisk role) | `website_asterisk_config_dir`, `website_asterisk_user`, `website_asterisk_group` |
| Let's Encrypt contact | `certbot_email` | `website_certbot_email` (set it to `"{{ certbot_email }}"`) |

Set the role variable once at the `all` layer and the applications follow.

## The zone and the host names

`website_domain` is the only value you have to choose for the applications to
get their addresses. Each application is served under a label in front of it:

| Application | Host name |
| --- | --- |
| `frontend` | `example.com` (the bare zone) |
| `auth` | `auth.example.com` |
| `backend` | `api.example.com` |
| `analytics` | `ua.example.com` |
| `apt_server` | `apt.example.com` |
| `knowledge`, `webhooks` | `<application>.example.com` |
| `mta_sts`, `vpn_portal` | `mta-sts.example.com`, `vpn.example.com` |
| `billing`, `mailler`, `team` | `<application>.internal` |
| `custom_domain`, `internal`, `reachy_mini_api` | `custom-domain.internal`, `admin.internal`, `reachy.internal` |

The labels are `website_subdomains_defaults`; change single ones with
`website_subdomains_overrides`, a whole host name with
`website_hostnames_overrides`, and the zone of the internal applications with
`website_internal_domain` and `website_internal_apps`. The catalog, the OAuth2
issuer and the Let's Encrypt requests all use the resulting
`website_hostnames`, so changing the zone updates everything consistently.

## Applications

The applications are configured by three variables, covered on
[Deploying applications](05-deploying-apps.md):

- `website_apps_enabled`: what to deploy;
- `website_apps_overrides`: what differs from the catalog;
- `website_secrets`: the secret values.

## Checking what a value is

```bash
# The value a host would use
ansible web -m ansible.builtin.debug -a 'var=website_hostnames'

# The overrides in effect
ansible web -m ansible.builtin.debug -a 'var=website_apps_overrides'

# What a run would change
ansible-playbook goabonga.website.apps --check --diff
```
