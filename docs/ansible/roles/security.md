# security

Harden the SSH daemon, optionally enable a ufw firewall and unattended upgrades.

Writes an sshd drop-in with configurable hardening options, can configure a ufw firewall and can enable unattended security upgrades. Every feature has its own toggle.

## Requirements

- Debian 12 or 13, Ubuntu 22.04 or 24.04.
- Privilege escalation (`become: true`).
- Collection `community.general` for the ufw module (only when the firewall is enabled).

## Variables

Every variable is optional and defined in `defaults/main.yml`. The role validates them against `meta/argument_specs.yml` before running.

### SSH daemon

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `security_ssh_enabled` | bool | `true` | Manage the sshd hardening drop-in. |
| `security_ssh_config_dir` | path | `"/etc/ssh/sshd_config.d"` | Directory of sshd drop-in files. |
| `security_ssh_config_name` | str | `"99-hardening.conf"` | File name of the drop-in written by this role. |
| `security_ssh_service` | str | `"ssh"` | Name of the systemd unit of the SSH daemon (ssh on Debian and Ubuntu). |
| `security_ssh_validate` | bool | `true` | Validate the drop-in with sshd -t before installing it. |
| `security_ssh_remove_cloud_init` | bool | `true` | Remove the cloud-init sshd drop-in that may override the hardening. |
| `security_ssh_cloud_init_file` | str | `"50-cloud-init.conf"` | Name of the cloud-init drop-in removed when security_ssh_remove_cloud_init is true. |
| `security_ssh_port` | int | `22` | TCP port sshd listens on. |
| `security_ssh_permit_root_login` | str | `"prohibit-password"` | Value of PermitRootLogin. Choices: `yes`, `no`, `prohibit-password`, `forced-commands-only`. |
| `security_ssh_password_authentication` | bool | `false` | Allow password authentication. |
| `security_ssh_kbd_interactive_authentication` | bool | `false` | Allow keyboard-interactive authentication. |
| `security_ssh_pubkey_authentication` | bool | `true` | Allow public key authentication. |
| `security_ssh_x11_forwarding` | bool | `false` | Allow X11 forwarding. |
| `security_ssh_allow_tcp_forwarding` | bool | `true` | Allow TCP forwarding. |
| `security_ssh_use_dns` | bool | `false` | Resolve client host names (UseDNS). |
| `security_ssh_max_auth_tries` | int | `3` | Maximum authentication attempts per connection. |
| `security_ssh_login_grace_time` | int | `30` | Seconds allowed to authenticate before the connection is dropped. |
| `security_ssh_client_alive_interval` | int | `300` | Seconds between keep-alive probes (0 disables). |
| `security_ssh_client_alive_count_max` | int | `2` | Unanswered keep-alive probes before disconnecting. |
| `security_ssh_allow_users` | list of str | `[]` | AllowUsers patterns. Nothing is emitted when empty. |
| `security_ssh_allow_groups` | list of str | `[]` | AllowGroups patterns. Nothing is emitted when empty. |
| `security_ssh_extra_options` | list of str | `[]` | Extra raw sshd options, one per item, for example 'LogLevel VERBOSE'. |

### Firewall

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `security_firewall_enabled` | bool | `false` | Install and configure the ufw firewall. |
| `security_firewall_default_incoming` | str | `"deny"` | Default policy for incoming traffic. Choices: `allow`, `deny`, `reject`. |
| `security_firewall_default_outgoing` | str | `"allow"` | Default policy for outgoing traffic. Choices: `allow`, `deny`, `reject`. |
| `security_firewall_allow_ssh` | bool | `true` | Allow the SSH port (security_ssh_port) so enabling the firewall cannot lock you out. |
| `security_firewall_logging` | str | `"low"` | ufw logging level. Choices: `on`, `off`, `low`, `medium`, `high`, `full`. |
| `security_firewall_rules` | list of dict | `[]` | Additional ufw rules. |

Keys of each `security_firewall_rules` item:

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `port` | str | yes | Port or port range (for example 443 or 10000:20000). |
| `proto` | str | no | Protocol (default tcp). Choices: `tcp`, `udp`, `any`. |
| `rule` | str | no | Action (default allow). Choices: `allow`, `deny`, `reject`, `limit`. |
| `from_ip` | str | no | Source address or network (default any). |
| `comment` | str | no | Rule comment. |

### Unattended upgrades

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `security_unattended_upgrades_enabled` | bool | `false` | Install and enable unattended-upgrades. |
| `security_unattended_upgrades_auto_reboot` | bool | `false` | Reboot automatically when an upgrade requires it. |
| `security_unattended_upgrades_reboot_time` | str | `"03:00"` | Time of the automatic reboot (HH:MM). |
| `security_unattended_upgrades_remove_unused` | bool | `true` | Remove unused dependencies after upgrading. |
| `security_unattended_upgrades_mail` | str | `""` | Address that receives upgrade reports. Disabled when empty. |
| `security_unattended_upgrades_update_interval` | int | `1` | Days between package list updates. |
| `security_unattended_upgrades_upgrade_interval` | int | `1` | Days between unattended upgrades. |

## Behavior

- SSH hardening is written to a drop-in file in `sshd_config.d`, so the distribution `sshd_config` is never edited. The drop-in is read before the rest of the configuration, which makes its values win.
- The drop-in is validated with `sshd -t` before being installed and sshd is restarted only when it changed.
- Options that are empty (`AllowUsers`, `AllowGroups`) are not emitted at all.
- Changing `security_ssh_port` does not update the firewall by itself except through `security_firewall_allow_ssh`; the previous port rule stays until you remove it.
- The firewall allows the SSH port before applying default policies and enabling ufw, to avoid locking the session out.
- Unattended upgrades use the distribution default origins; the role only layers reboot, cleanup and mail settings on top.

## Tags

| Tag | Scope |
| --- | --- |
| `security` | Every task of the role. |
| `security_ssh` | SSH daemon hardening. |
| `security_firewall` | ufw firewall. |
| `security_unattended_upgrades` | Automatic upgrades. |

## Example

```yaml
- hosts: all
  become: true
  roles:
    - role: goabonga.website.security
      vars:
        security_ssh_port: 2222
        security_ssh_allow_users: [deploy]
        security_firewall_enabled: true
        security_firewall_rules:
          - {port: 80, proto: tcp}
          - {port: 443, proto: tcp}
        security_unattended_upgrades_enabled: true
```

## See also

- Make sure the `users` role has authorized a key before disabling password authentication.
