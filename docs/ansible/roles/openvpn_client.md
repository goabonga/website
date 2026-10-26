# openvpn_client

Connects a host to an OpenVPN server. It installs OpenVPN, deploys a client
profile (`.ovpn`) from the controller as `/etc/openvpn/<name>.conf`, wires the
tunnel to systemd-resolved so the VPN DNS servers apply while it is up, and
runs it as an `openvpn@<name>` service that restarts on failure. The profile
itself comes from the [openvpn](openvpn.md) role, which exports one per client.

## Requirements

- A Debian-family target (the role asserts `os_family == Debian`).
- A client profile on the controller. Without `openvpn_client_config_file` the
  role only installs OpenVPN and does not start a tunnel. When the variable is
  set and the file is missing the role stops before changing anything.
- `systemd-resolved` on the host for the DNS integration (disable it with
  `openvpn_client_dns_integration: false` otherwise).

## Usage

```yaml
- hosts: laptops
  become: true
  roles:
    - role: goabonga.website.openvpn_client
      vars:
        openvpn_client_config_file: "{{ playbook_dir }}/files/openvpn-clients/laptop.ovpn"
```

Profile only, managed by hand, without DNS integration:

```yaml
- hosts: laptops
  become: true
  roles:
    - role: goabonga.website.openvpn_client
      vars:
        openvpn_client_config_file: /srv/profiles/laptop.ovpn
        openvpn_client_dns_integration: false
        openvpn_client_service_state: stopped
        openvpn_client_autostart: false
```

Run it alone with `--tags openvpn_client`.

## What it does

1. Validates the target and the profile path.
2. Installs `openvpn` and, with the DNS integration, `openvpn-systemd-resolved`,
   and starts `systemd-resolved` (unless `openvpn_client_manage_resolved` is
   false).
3. Reads the profile on the controller and installs it with mode `0600`,
   followed by the `up`/`down` directives of the DNS script and the entries of
   `openvpn_client_extra_config`. The diff is hidden because the profile embeds
   the client key.
4. Deploys a drop-in making the unit restart on failure, or removes it when
   `openvpn_client_restart_on_failure` is false.
5. Enables and starts `openvpn@<name>` according to `openvpn_client_autostart`
   and `openvpn_client_service_state`.

A change of the profile restarts the tunnel.

## Variables

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_client_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `openvpn_client_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages. |
| `openvpn_client_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### Installation

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_client_packages` | list | `[openvpn]` | Packages to install. |
| `openvpn_client_dns_integration` | bool | `true` | Update the DNS settings of the host through systemd-resolved while the tunnel is up. |
| `openvpn_client_dns_packages` | list | `[openvpn-systemd-resolved]` | Packages providing the DNS update script, installed with dns_integration. |
| `openvpn_client_dns_script` | path | `"/etc/openvpn/update-systemd-resolved"` | DNS update script run on tunnel up and down. |
| `openvpn_client_manage_resolved` | bool | `true` | Start and enable systemd-resolved when DNS integration is on. |

### Profile

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_client_config_file` | path | `""` | Client profile (.ovpn) on the controller. Empty installs OpenVPN without a profile and without starting the tunnel. |
| `openvpn_client_config_name` | str | `"client"` | Name of the tunnel: the profile is installed as /etc/openvpn/<name>.conf and run by openvpn@<name>. |
| `openvpn_client_config_dir` | path | `"/etc/openvpn"` | Directory receiving the profile. |
| `openvpn_client_extra_config` | list | `[]` | Additional directives appended to the profile, one per entry. |

### Service

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_client_service_state` | str | `"started"` | State of the tunnel service. |
| `openvpn_client_autostart` | bool | `true` | Enable the tunnel at boot. |
| `openvpn_client_restart_on_failure` | bool | `true` | Add a systemd drop-in restarting the tunnel when it fails. When false the drop-in is removed. |
| `openvpn_client_restart_sec` | int | `10` | RestartSec= of the drop-in. |


## Handlers

| Topic | Effect |
| --- | --- |
| `openvpn_client \| reload systemd` | Runs `systemctl daemon-reload`. |
| `openvpn_client \| restart` | Restarts `openvpn@<name>` (only when a profile is set and the state is `started`). |

## Verification status

The role is checked with `ansible-playbook --syntax-check`, the argument
specification is validated against the defaults and the profile and drop-in
templates are rendered locally. It has not been run against a live host: package
installation, the DNS update script and an actual tunnel are untested.
