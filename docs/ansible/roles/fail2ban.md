# fail2ban

Install fail2ban with an SSH jail, optional nginx and Asterisk jails, custom jails and filters.

Installs fail2ban, writes the global defaults to jail.local and renders jails and filters from variables: a configurable sshd jail, ready-made nginx and Asterisk jails and any number of custom jails and filters, so other roles can protect their own logs without editing templates.

## Requirements

- Debian 12 or 13, Ubuntu 22.04 or 24.04.
- Privilege escalation (`become: true`).

## Variables

Every variable is optional and defined in `defaults/main.yml`. The role validates them against `meta/argument_specs.yml` before running.

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `fail2ban_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `fail2ban_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages. |
| `fail2ban_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### Installation and service

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `fail2ban_packages` | list of str | `["fail2ban"]` | Packages to install. |
| `fail2ban_service_name` | str | `"fail2ban"` | systemd unit name. |
| `fail2ban_service_state` | str | `"started"` | State of the service after configuration. Choices: `started`, `stopped`. |
| `fail2ban_service_enabled` | bool | `true` | Enable the service at boot. |
| `fail2ban_config_dir` | path | `"/etc/fail2ban"` | Fail2ban configuration directory. |
| `fail2ban_test_config` | bool | `true` | Run fail2ban-client --test after writing the configuration. |

### Global defaults

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `fail2ban_bantime` | str | `"1h"` | Default ban duration. |
| `fail2ban_findtime` | str | `"10m"` | Default window in which failures are counted. |
| `fail2ban_maxretry` | int | `5` | Default number of failures before a ban. |
| `fail2ban_ignoreip` | list of str | `["127.0.0.1/8", "::1"]` | Addresses and networks that are never banned, for example a VPN network. |
| `fail2ban_backend` | str | `"auto"` | Default log backend. Choices: `auto`, `pyinotify`, `gamin`, `polling`, `systemd`. |
| `fail2ban_banaction` | str | `""` | Default ban action for single ports, for example iptables-multiport. The distribution default is kept when empty. |
| `fail2ban_banaction_allports` | str | `""` | Default ban action for all ports, for example iptables-allports. The distribution default is kept when empty. |
| `fail2ban_destemail` | str | `""` | Address that receives notifications. Not set when empty. |

### SSH jail

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `fail2ban_ssh_enabled` | bool | `true` | Enable the sshd jail. |
| `fail2ban_ssh_port` | str | `"ssh"` | Port or service name protected by the sshd jail. Set it to your custom SSH port. |
| `fail2ban_ssh_maxretry` | int | `3` | Failures before a ban in the sshd jail. |
| `fail2ban_ssh_bantime` | str | `"1h"` | Ban duration in the sshd jail. |
| `fail2ban_ssh_findtime` | str | `""` | Failure window in the sshd jail. The default findtime is used when empty. |
| `fail2ban_ssh_logpath` | str | `""` | Log file of the sshd jail. The distribution default is used when empty. |

### nginx jails

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `fail2ban_nginx_enabled` | bool | `false` | Enable the nginx jails (nginx-http-auth, nginx-botsearch and nginx-badbots). |
| `fail2ban_nginx_port` | str | `"http,https"` | Ports protected by the nginx jails. |
| `fail2ban_nginx_maxretry` | int | `5` | Failures before a ban in the nginx-http-auth and nginx-botsearch jails. |
| `fail2ban_nginx_badbots_maxretry` | int | `2` | Failures before a ban in the nginx-badbots jail. |
| `fail2ban_nginx_bantime` | str | `"1h"` | Ban duration of the nginx jails. |
| `fail2ban_nginx_findtime` | str | `"10m"` | Failure window of the nginx jails. |
| `fail2ban_nginx_access_log` | path | `"/var/log/nginx/access.log"` | Access log watched by the nginx-botsearch and nginx-badbots jails. |
| `fail2ban_nginx_error_log` | path | `"/var/log/nginx/error.log"` | Error log watched by the nginx-http-auth jail. |

### Asterisk jail

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `fail2ban_asterisk_enabled` | bool | `false` | Enable the Asterisk jail and install its filter. |
| `fail2ban_asterisk_port` | str | `"5060,5061"` | Ports protected by the Asterisk jail. |
| `fail2ban_asterisk_protocol` | str | `"udp"` | Protocol protected by the Asterisk jail. Choices: `tcp`, `udp`. |
| `fail2ban_asterisk_maxretry` | int | `3` | Failures before a ban in the Asterisk jail. |
| `fail2ban_asterisk_bantime` | str | `"24h"` | Ban duration of the Asterisk jail. |
| `fail2ban_asterisk_findtime` | str | `"10m"` | Failure window of the Asterisk jail. |
| `fail2ban_asterisk_logpath` | path | `"/var/log/asterisk/messages.log"` | Log file watched by the Asterisk jail. |

### Custom jails and filters

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `fail2ban_jails` | list of dict | `[]` | Additional jails, each written to its own file in jail.d. |
| `fail2ban_filters` | list of dict | `[]` | Custom filters, each written to its own file in filter.d. |

Keys of each `fail2ban_jails` item:

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | str | yes | Jail name, also used for the file name. |
| `enabled` | bool | no | Enable the jail (default true). |
| `filter` | str | no | Filter name (default: the jail name). |
| `port` | str | no | Port, comma separated ports or service names. |
| `protocol` | str | no | Protocol (tcp or udp). |
| `logpath` | str | no | Log file to watch. |
| `backend` | str | no | Log backend of this jail. |
| `maxretry` | int | no | Failures before a ban. |
| `bantime` | str | no | Ban duration. |
| `findtime` | str | no | Failure window. |
| `banaction` | str | no | Ban action. |
| `action` | str | no | Full action string, overrides banaction. |
| `extra` | list of str | no | Raw option lines appended to the jail, for example 'ignorecommand = ...'. |

Keys of each `fail2ban_filters` item:

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | str | yes | Filter name, also used for the file name. |
| `before` | str | no | Filter file included first, for example common.conf. |
| `failregex` | list of str | yes | Regular expressions matching a failure. |
| `ignoreregex` | list of str | no | Regular expressions to ignore. |
| `datepattern` | str | no | Custom date pattern. |
| `daemon` | str | no | Value of _daemon, used by common.conf to match the log prefix. |
| `init` | dict | no | Options written in an [Init] section. |

## Behavior

- Global defaults and the sshd jail are written to `jail.local`. Each other jail and filter gets its own file in `jail.d` and `filter.d`, so removing one never touches the others.
- `fail2ban_ssh_port` must follow the SSH port set by the `security` role, otherwise the jail watches the wrong port.
- The ready-made nginx jails (`nginx-http-auth`, `nginx-botsearch`, `nginx-badbots`) and the Asterisk jail with its filter are opt-in. Turning a toggle off removes the files the role wrote for it.
- The `nginx-badbots` jail uses the `apache-badbots` filter shipped with fail2ban, which matches nginx combined logs as well.
- Optional keys that are not set on a custom jail or filter are not written, so the fail2ban defaults apply.
- The configuration is checked with `fail2ban-client --test`; any change restarts the service through the `fail2ban | restart` handler.

## Tags

| Tag | Scope |
| --- | --- |
| `fail2ban` | Every task of the role. |

## Example

```yaml
- hosts: all
  become: true
  roles:
    - role: goabonga.website.fail2ban
      vars:
        fail2ban_ssh_port: "2222"
        fail2ban_ignoreip: [127.0.0.1/8, "::1", 10.8.0.0/24]
        fail2ban_nginx_enabled: true
        fail2ban_filters:
          - name: myapp
            failregex: ['^<HOST> .* "POST /login HTTP/[0-9.]+" 401']
        fail2ban_jails:
          - name: myapp
            filter: myapp
            port: http,https
            logpath: /var/log/nginx/access.log
            maxretry: 10
```

## See also

- `nginx` role: enable `fail2ban_nginx_enabled` to protect the web server.
- `security` role: keep `fail2ban_ssh_port` aligned with `security_ssh_port`.
