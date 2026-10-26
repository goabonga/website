# asterisk

Installs Asterisk from the distribution packages and, on demand, wires it to a
SIP trunk: PJSIP transport, registration, endpoint and an inbound dialplan. It
can also open the SIP and RTP ports with iptables and ship a fail2ban jail for
PJSIP authentication failures. Everything about the trunk is provider
agnostic.

## Requirements

- A Debian-family target (the role asserts `os_family == Debian`).
- For the firewall rules: `iptables` on the target (the role uses the
  `ansible.builtin.iptables` module).
- For the jail: fail2ban installed on the host. The role does not install it
  and, by default, skips the jail when the client is missing.
- The credentials of a SIP account from your provider.

## Usage

Asterisk only, no trunk (the default):

```yaml
- hosts: pbx
  become: true
  roles:
    - role: goabonga.website.asterisk
```

A registered trunk that hands inbound calls to an application context, with the
firewall managed:

```yaml
- hosts: pbx
  become: true
  roles:
    - role: goabonga.website.asterisk
      vars:
        asterisk_trunk_enabled: true
        asterisk_trunk_server: sip.provider.example
        asterisk_trunk_username: "0033000000000"
        asterisk_trunk_password: "{{ vault_asterisk_trunk_password }}"
        asterisk_incoming_context: fastagi-bot
        asterisk_dids:
          - number: "0033111111111"
            description: Support line
            extension: PJSIP/100
        asterisk_firewall_enabled: true
```

Run it alone with `--tags asterisk`.

## What it does

1. Validates the target and, when the trunk is enabled, the trunk settings.
2. Installs Asterisk and its sound packages and marks the modules of
   `asterisk_noload_modules` as `noload` in `modules.conf`.
3. With `asterisk_trunk_enabled`: renders `pjsip_trunk.conf` (transport,
   registration, authentication, AOR, endpoint, identify) and
   `extensions_trunk.conf` (inbound dialplan), both mode `0640`, and adds an
   `#include` line for each to `pjsip.conf` and `extensions.conf`. When it is
   false the include lines and the two files are removed.
4. With `asterisk_firewall_enabled`: accepts the SIP port and the RTP range and
   saves the rule set to `asterisk_firewall_rules_file`.
5. Starts and enables the service, then applies the pending reloads.
6. Deploys the fail2ban filter and jail, or removes them when
   `asterisk_fail2ban_enabled` is false.

## Inbound dialplan

Calls arriving on the trunk enter the context `asterisk_trunk_context`:

- Without `asterisk_incoming_context` every call answers, plays
  `asterisk_incoming_sound` and hangs up.
- With it, calls jump to `<context>,s,1`.
- Each entry of `asterisk_dids` adds a dedicated route: `context` jumps to
  `<context>,s,1`, `extension` dials the endpoint for
  `asterisk_did_dial_timeout` seconds, and an entry with neither follows the
  default behaviour above.

## Registration and IP-authenticated trunks

By default the account registers with the provider (`asterisk_trunk_register`).
Set it to `false` for a provider that authenticates by source address: the
registration section is dropped, the endpoint and the identify section stay.

## Fail2ban

The jail and filter are named `asterisk-pjsip` (`asterisk_fail2ban_jail_name`)
on purpose: fail2ban ships its own `asterisk` filter and the role never
overwrites a file owned by a package. The filter matches PJSIP registration,
authentication and unknown-endpoint failures in `messages.log`; make sure
Asterisk logs `notice`, `warning` and `security` messages to that file.

## Variables

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `asterisk_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `asterisk_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages. |
| `asterisk_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### Installation and service

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `asterisk_packages` | list | `[asterisk, asterisk-core-sounds-en, asterisk-core-sounds-fr]` | Packages to install. |
| `asterisk_user` | str | `"asterisk"` | Owner of the generated configuration files. |
| `asterisk_group` | str | `"asterisk"` | Group of the generated configuration files. |
| `asterisk_config_dir` | path | `"/etc/asterisk"` | Asterisk configuration directory. |
| `asterisk_service_name` | str | `"asterisk"` | systemd unit name. |
| `asterisk_service_state` | str | `"started"` | State of the service after configuration. |
| `asterisk_service_enabled` | bool | `true` | Enable the service at boot. |
| `asterisk_noload_modules` | list | `[cel_radius.so, cdr_radius.so]` | Modules marked `noload` in modules.conf. |

### SIP transport

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `asterisk_transport_manage` | bool | `true` | Declare the PJSIP transport together with the trunk. Disable it when pjsip.conf already defines one. |
| `asterisk_transport_name` | str | `"transport-udp"` | Name of the PJSIP transport section. |
| `asterisk_transport_protocol` | str | `"udp"` | Transport protocol. |
| `asterisk_transport_bind_address` | str | `"0.0.0.0"` | Address the transport binds to. |
| `asterisk_transport_port` | int | `5060` | Port the transport binds to; also the port opened by the firewall and watched by fail2ban. |

### SIP trunk

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `asterisk_trunk_enabled` | bool | `false` | Configure the SIP trunk and the inbound dialplan. When false their files and include lines are removed. |
| `asterisk_trunk_name` | str | `"trunk"` | Prefix of the PJSIP sections (<name>-auth, <name>-aor, <name>-endpoint, ...). |
| `asterisk_trunk_server` | str | `""` | SIP server (host name) of the provider. Required when the trunk is enabled. |
| `asterisk_trunk_username` | str | `""` | SIP account / number registered with the provider. Required when the trunk is enabled. |
| `asterisk_trunk_password` | str | `""` | SIP account password. Required when the trunk is enabled. Provide it from a vault. |
| `asterisk_trunk_register` | bool | `true` | Register the account with the provider. Disable for IP-authenticated trunks. |
| `asterisk_trunk_retry_interval` | int | `60` | Seconds between registration retries. |
| `asterisk_trunk_expiration` | int | `3600` | Registration expiration in seconds. |
| `asterisk_trunk_qualify_frequency` | int | `60` | Seconds between qualify (keep-alive) requests to the provider. |
| `asterisk_trunk_codecs` | list | `[alaw, ulaw, g722]` | Codecs allowed on the trunk, in order of preference. |
| `asterisk_trunk_context` | str | `"from-trunk"` | Dialplan context receiving inbound calls. |
| `asterisk_trunk_extra_endpoint_options` | dict | `{}` | Additional PJSIP endpoint options rendered as `key=value`, for example {dtmf_mode: rfc4733}. |
| `asterisk_trunk_pjsip_file` | str | `"pjsip_trunk.conf"` | File (relative to the configuration directory) holding the generated PJSIP sections; it is included from pjsip.conf. |
| `asterisk_trunk_dialplan_file` | str | `"extensions_trunk.conf"` | File (relative to the configuration directory) holding the generated dialplan; it is included from extensions.conf. |

### Inbound calls

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `asterisk_incoming_context` | str | `""` | Dialplan context that receives calls without a more specific route, for example the context of an AGI application. Empty plays a sound and hangs up. |
| `asterisk_incoming_sound` | str | `"hello-world"` | Sound played when no incoming context is set. |
| `asterisk_dids` | list | `[]` | Per-number routes. |
| `asterisk_did_dial_timeout` | int | `30` | Seconds to ring an endpoint for DID routes using `extension`. |

### Firewall

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `asterisk_firewall_enabled` | bool | `false` | Open the SIP and RTP ports with iptables. |
| `asterisk_firewall_chain` | str | `"INPUT"` | iptables chain receiving the rules. |
| `asterisk_firewall_rtp_ports` | str | `"10000:20000"` | RTP port range to open. It must match rtp.conf. |
| `asterisk_firewall_persist` | bool | `true` | Save the rule set after a change. |
| `asterisk_firewall_rules_file` | path | `"/etc/iptables/rules.v4"` | File receiving the saved rule set (iptables-persistent format). |

### Fail2ban

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `asterisk_fail2ban_enabled` | bool | `true` | Deploy the fail2ban filter and jail. When false they are removed. |
| `asterisk_fail2ban_require_installed` | bool | `true` | Deploy only when the fail2ban client is present, so the role never depends on the fail2ban role. |
| `asterisk_fail2ban_client` | path | `"/usr/bin/fail2ban-client"` | Path of the fail2ban client used to detect an installation. |
| `asterisk_fail2ban_service_name` | str | `"fail2ban"` | systemd unit reloaded after a change. |
| `asterisk_fail2ban_jail_name` | str | `"asterisk-pjsip"` | Name of the jail and of the filter. It differs from the `asterisk` filter shipped by fail2ban on purpose. |
| `asterisk_fail2ban_filter_dir` | path | `"/etc/fail2ban/filter.d"` | Directory receiving the filter. |
| `asterisk_fail2ban_jail_dir` | path | `"/etc/fail2ban/jail.d"` | Directory receiving the jail. |
| `asterisk_fail2ban_logpath` | path | `"/var/log/asterisk/messages.log"` | Log file watched by the jail. |
| `asterisk_fail2ban_ports` | str | `"5060,5061"` | Ports banned by the jail. |
| `asterisk_fail2ban_protocol` | str | `"udp"` | Protocol banned by the jail. |
| `asterisk_fail2ban_maxretry` | int | `3` | Failures before a ban. |
| `asterisk_fail2ban_findtime` | str | `"10m"` | Window in which failures are counted. |
| `asterisk_fail2ban_bantime` | str | `"24h"` | Duration of a ban. |


## Handlers

| Topic | Effect |
| --- | --- |
| `asterisk \| reload` | Reloads the service (only when `asterisk_service_state` is `started`). |
| `asterisk \| restart` | Restarts the service (only when `asterisk_service_state` is `started`). |
| `asterisk \| save iptables` | Runs `iptables-save` into `asterisk_firewall_rules_file` when `asterisk_firewall_persist` is true. |
| `asterisk \| reload fail2ban` | Reloads fail2ban when its client was found. |

## Verification status

The role is checked with `ansible-playbook --syntax-check`, the argument
specification is validated against the defaults and all templates are rendered
locally with sample values. It has not been run against a live host: package
installation, the `modules.conf` and include-line edits, the iptables rules,
the fail2ban reload and a real SIP registration are untested.
