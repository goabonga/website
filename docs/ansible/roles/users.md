# users

Create the deploy user and additional user accounts with SSH keys and sudo rules.

Manages operating system accounts: an optional deploy account used by application deployments plus any number of additional accounts, each with groups, authorized keys and a sudo policy.

## Requirements

- Debian 12 or 13, Ubuntu 22.04 or 24.04.
- Privilege escalation (`become: true`).
- Collection `ansible.posix` for authorized keys.

## Variables

Every variable is optional and defined in `defaults/main.yml`. The role validates them against `meta/argument_specs.yml` before running.

### Deploy account

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `users_deploy_enabled` | bool | `true` | Create the deploy account used by application deployments. |
| `users_deploy_name` | str | `"deploy"` | Login name of the deploy account. |
| `users_deploy_shell` | str | `"/bin/bash"` | Login shell of the deploy account. |
| `users_deploy_groups` | list of str | `[]` | Supplementary groups of the deploy account (appended, never replaced). |
| `users_deploy_ssh_public_keys` | list of str | `[]` | SSH public keys (full key lines) authorized for the deploy account. |
| `users_deploy_sudo` | str | `"nopasswd"` | Sudo policy of the deploy account: none removes any rule, nopasswd grants passwordless sudo, password grants sudo with a password. Choices: `none`, `nopasswd`, `password`. |
| `users_deploy_password_hash` | str | `""` | Password hash for the deploy account (required when users_deploy_sudo is password). Keep it in an Ansible Vault. |

### Additional accounts

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `users_accounts` | list of dict | `[]` | Additional accounts to manage. |

Keys of each `users_accounts` item:

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | str | yes | Login name. |
| `state` | str | no | present (default) or absent. Choices: `present`, `absent`. |
| `shell` | str | no | Login shell (default /bin/bash). |
| `groups` | list of str | no | Supplementary groups (appended). |
| `comment` | str | no | GECOS comment. |
| `uid` | int | no | Fixed numeric user id. |
| `system` | bool | no | Create a system account. |
| `home` | str | no | Home directory path. |
| `create_home` | bool | no | Create the home directory (default true). |
| `remove` | bool | no | Remove the home directory when state is absent. |
| `password_hash` | str | no | Password hash (use a Vault). |
| `ssh_public_keys` | list of str | no | SSH public keys to authorize. |
| `ssh_exclusive` | bool | no | Remove authorized keys that are not listed. |
| `sudo` | str | no | Sudo policy (default none). Choices: `none`, `nopasswd`, `password`. |

### Other settings

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `users_sudoers_dir` | path | `"/etc/sudoers.d"` | Directory holding the per-user sudoers files. |
| `users_install_sudo` | bool | `true` | Install the sudo package when at least one account has a sudo policy. |
| `users_default_shell` | str | `"/bin/bash"` | Shell used for additional accounts that do not set one. |

## Behavior

- The deploy account and every entry of `users_accounts` go through the same code path, so they support the same keys.
- Groups are appended to the account; existing memberships are never removed.
- Public keys are provided as key lines, not as file paths, so they can come from inventory, a Vault or a `lookup('file', ...)` evaluated on the controller.
- `ssh_exclusive: true` removes every authorized key that is not listed.
- Each account has a file in the sudoers directory, validated with `visudo -cf`. The policy `none` removes the file.
- The `password` sudo policy requires a `password_hash`; the role stops before touching the host when it is missing.
- Tasks that handle password hashes run with `no_log`.

## Tags

| Tag | Scope |
| --- | --- |
| `users` | Every task of the role. |

## Example

```yaml
- hosts: all
  become: true
  roles:
    - role: goabonga.website.users
      vars:
        users_deploy_name: deploy
        users_deploy_ssh_public_keys:
          - "ssh-ed25519 AAAA... ops@example.com"
        users_accounts:
          - name: alice
            groups: [adm]
            sudo: password
            password_hash: "{{ vault_alice_password_hash }}"
            ssh_public_keys:
              - "ssh-ed25519 AAAA... alice@example.com"
```
