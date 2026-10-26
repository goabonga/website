# openvpn

Runs an OpenVPN server. The role builds the PKI (Easy-RSA, or certificates
issued by a [step_ca](step_ca.md) authority), renders the server configuration,
enables forwarding and NAT, creates the clients with their certificates, static
addresses and ready-to-use `.ovpn` profiles, and can run a dedicated dnsmasq
resolver for the VPN and publish step-ca on the VPN address. The profiles it
exports are consumed by the [openvpn_client](openvpn_client.md) role.

## Requirements

- A Debian-family target (the role asserts `os_family == Debian`) with gathered
  facts: the NAT interface comes from `ansible_facts['default_ipv4']`.
- The `ansible.posix` collection on the controller (a dependency of
  `goabonga.website`) for the sysctl module.
- With `openvpn_pki_backend: step-ca`: a step-ca authority on the same host (the
  `step_ca` role), its root certificate and a provisioner password. Without
  them the role falls back to Easy-RSA unless `openvpn_pki_fallback` is false.
- For `openvpn_stepca_nginx_enabled`: nginx installed and a certificate for the
  step-ca domain, as produced by the `step_ca` role with its nginx proxy.

## Usage

Easy-RSA PKI, two clients with static addresses:

```yaml
- hosts: vpn
  become: true
  roles:
    - role: goabonga.website.openvpn
      vars:
        openvpn_server_public_address: vpn.example.net
        openvpn_clients:
          - name: laptop
            ip: 10.8.0.10
          - name: nas
            ip: 10.8.0.50
            aliases:
              - nas.internal
```

Certificates from step-ca, with step-ca reachable by the clients through the
VPN:

```yaml
- hosts: vpn
  become: true
  roles:
    - role: goabonga.website.step_ca
      vars:
        step_ca_password: "{{ vault_step_ca_password }}"
    - role: goabonga.website.openvpn
      vars:
        openvpn_pki_backend: step-ca
        openvpn_stepca_password: "{{ vault_openvpn_stepca_password }}"
        openvpn_stepca_nginx_enabled: true
        openvpn_clients:
          - name: laptop
            ip: 10.8.0.10
```

Run it alone with `--tags openvpn`.

## What it does

1. Validates the target, the client names (letters, digits, `.`, `_`, `-`; they
   are used in file names and commands) and the NAT interface.
2. Installs OpenVPN and the firewall persistence package, and creates the
   server, `ccd` and log directories.
3. Chooses the PKI backend, builds it, and generates the `tls-auth` key:
   - Easy-RSA: initialises the PKI, builds an unprotected CA, issues the server
     certificate and generates the Diffie-Hellman parameters.
   - step-ca: installs `step-cli`, writes the provisioner password file, creates
     or updates the JWK provisioner in `ca.json` (unless
     `openvpn_stepca_manage_provisioner` is false), requests the server
     certificate and installs the root certificate. `dh none` is used.
4. Renders `/etc/openvpn/server/<name>.conf`.
5. Enables IPv4 forwarding and adds a `MASQUERADE` rule for the VPN network on
   the outgoing interface, then saves the rule set.
6. Starts and enables `openvpn-server@<name>`.
7. For each client: writes `ifconfig-push` in the `ccd` directory, issues the
   certificate, renders the profile in `openvpn_clients_dir` (mode `0600`) and,
   with `openvpn_clients_export_enabled`, fetches it into
   `openvpn_clients_export_dir` on the controller.
8. With `openvpn_dns_enabled`: installs dnsmasq and runs a second instance
   (`dnsmasq-vpn`) bound to the VPN address, serving `<client>.<domain>` for
   every client with a static address, their aliases and `openvpn_dns_hosts`.
   The unit is bound to the OpenVPN service.
9. With `openvpn_stepca_nginx_enabled`: names step-ca in the VPN resolver and
   publishes it through nginx on the VPN address.

Certificate generation is guarded by the presence of the files, so a second run
changes nothing.

In a check run (`--check`) nothing is fetched, so the mode of an exported profile
is checked only when the file already exists on the controller.

## Behaviour to know about

- The blocks that other roles add to the server configuration between
  `# BEGIN ANSIBLE MANAGED` and `# END ANSIBLE MANAGED` markers (the hooks of the
  `vpn_portal` application, added by `python_app`) are read back and rendered
  before the `status` line, so the role does not remove them and each run of
  either role changes nothing.
- The exported profiles embed the client private keys. Keep
  `openvpn_clients_export_dir` out of version control or encrypt it. The role
  restricts the files to mode `0600`.
- Static addresses are written for `topology subnet`, which the role sets by
  default and enforces when a client has an `ip`.
- Certificates are not renewed and revocation is not managed. Easy-RSA
  certificates last `openvpn_easyrsa_cert_expire` days; step-ca certificates
  last `openvpn_stepca_cert_duration` (one year by default): remove the
  certificate files to have them issued again.
- `openvpn_stepca_manage_provisioner` and the `step_ca_provisioners` list of the
  step_ca role can both describe the `openvpn` provisioner. Use only one of
  them.
- The Debian `dnsmasq` package also starts a general instance. If it conflicts
  with `openvpn_dns_listen_address` on port 53, bind or disable it separately;
  `openvpn_dns_publish_to_main` copies the client records to that instance.
- `explicit-exit-notify` is only written for UDP protocols.

## Variables

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `openvpn_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages. |
| `openvpn_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### Installation

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_packages` | list | `[openvpn]` | Packages to install. |
| `openvpn_firewall_packages` | list | `[iptables-persistent]` | Packages providing iptables rule persistence. Empty installs nothing. |

### Server

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_server_name` | str | `"server"` | Name of the server instance: the configuration is /etc/openvpn/server/<name>.conf and the unit openvpn-server@<name>. |
| `openvpn_config_dir` | path | `"/etc/openvpn/server"` | Directory holding the server configuration, certificates and keys. The openvpn-server@ unit reads /etc/openvpn/server: change it only if you provide your own unit. |
| `openvpn_ccd_dir` | path | `"{{ openvpn_config_dir }}/ccd"` | Client configuration directory holding the static address of each client. |
| `openvpn_port` | int | `1194` | Listening port. |
| `openvpn_proto` | str | `"udp"` | Transport protocol. |
| `openvpn_dev` | str | `"tun"` | Virtual device type or name. |
| `openvpn_topology` | str | `"subnet"` | Addressing topology. `subnet` is required for the static addresses written for the clients. |
| `openvpn_server_network` | str | `"10.8.0.0"` | VPN network address. |
| `openvpn_server_netmask` | str | `"255.255.255.0"` | VPN network mask. |
| `openvpn_cipher` | str | `"AES-256-GCM"` | Data channel cipher. |
| `openvpn_auth` | str | `"SHA256"` | HMAC digest. |
| `openvpn_tls_version_min` | str | `"1.2"` | Minimum TLS version. Empty leaves the OpenVPN default. |
| `openvpn_user` | str | `"nobody"` | User the server drops privileges to. |
| `openvpn_group` | str | `"nogroup"` | Group the server drops privileges to. |
| `openvpn_keepalive` | str | `"10 120"` | keepalive directive (ping interval and timeout). |
| `openvpn_client_to_client` | bool | `true` | Let clients reach each other. |
| `openvpn_redirect_gateway` | bool | `true` | Push a default route so client traffic goes through the VPN. |
| `openvpn_push_routes` | list | `[]` | Extra routes pushed to clients, each as `network netmask`. |
| `openvpn_dns_servers` | list | `['{{ openvpn_dns_listen_address }}']` | DNS servers pushed to clients. |
| `openvpn_push_domain` | str | `"internal"` | DNS search domain pushed to clients. Empty pushes none. |
| `openvpn_verbosity` | int | `3` | Log verbosity (verb). |
| `openvpn_log_dir` | path | `"/var/log/openvpn"` | Directory holding the log, status and address pool files. |
| `openvpn_extra_config` | list | `[]` | Raw directives appended to the server configuration, one per entry. |
| `openvpn_service_state` | str | `"started"` | State of the server service. |
| `openvpn_service_enabled` | bool | `true` | Enable the server service at boot. |

### Routing and NAT

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_ip_forward` | bool | `true` | Enable IPv4 forwarding. |
| `openvpn_sysctl_file` | path | `"/etc/sysctl.d/99-openvpn.conf"` | File persisting the forwarding setting. |
| `openvpn_nat_enabled` | bool | `true` | Masquerade the traffic of the VPN network. |
| `openvpn_nat_interface` | str | `""` | Outgoing interface of the NAT rule. Empty uses the default IPv4 interface reported by Ansible. |
| `openvpn_firewall_persist` | bool | `true` | Save the rule set after a change. |
| `openvpn_firewall_rules_file` | path | `"/etc/iptables/rules.v4"` | File receiving the saved rule set (iptables-persistent format). |

### PKI

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_pki_backend` | str | `"easyrsa"` | Certificate authority issuing the server and client certificates. |
| `openvpn_pki_fallback` | bool | `true` | Fall back to Easy-RSA when step-ca is requested but its root certificate or the provisioner password is missing. When false the role fails instead. |

### Easy-RSA PKI

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_easyrsa_package` | str | `"easy-rsa"` | Package providing Easy-RSA. |
| `openvpn_easyrsa_dir` | path | `"/etc/openvpn/easy-rsa"` | Easy-RSA working directory and PKI location. |
| `openvpn_easyrsa_dn_mode` | str | `"cn_only"` | EASYRSA_DN: distinguished name mode. |
| `openvpn_easyrsa_key_size` | int | `2048` | RSA key size. |
| `openvpn_easyrsa_ca_expire` | int | `3650` | Validity of the CA certificate in days. |
| `openvpn_easyrsa_cert_expire` | int | `3650` | Validity of the issued certificates in days. |
| `openvpn_easyrsa_ca_cn` | str | `"OpenVPN-CA"` | Common name of the CA. |

### step-ca PKI

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_stepca_package` | str | `"step-cli"` | Package providing the step command. |
| `openvpn_stepca_url` | str | `"{{ step_ca_url \| default('https://127.0.0.1:8443') }}"` | URL of the step-ca authority. Follows the step_ca role when it ran in the same play. |
| `openvpn_stepca_root_ca` | path | `"/etc/step-ca/certs/root_ca.crt"` | Root certificate of the authority on this host. |
| `openvpn_stepca_provisioner` | str | `"openvpn"` | Name of the JWK provisioner used to issue certificates. |
| `openvpn_stepca_password` | str | `""` | Password of the provisioner key. Required for the step-ca backend. Provide it from a vault. |
| `openvpn_stepca_password_file` | path | `"/etc/step-ca/secrets/openvpn-password"` | File holding the provisioner password, written by the role. |
| `openvpn_stepca_manage_provisioner` | bool | `true` | Create or update the provisioner in the authority from this role. Disable it when the step_ca role manages the provisioner. |
| `openvpn_stepca_home` | path | `"/etc/step-ca"` | STEPPATH of the authority on this host. |
| `openvpn_stepca_config_file` | path | `"/etc/step-ca/config/ca.json"` | ca.json of the authority on this host. |
| `openvpn_stepca_user` | str | `"step"` | User owning the authority files and running the step commands that edit ca.json. |
| `openvpn_stepca_group` | str | `"step"` | Group owning the password file. |
| `openvpn_stepca_service_name` | str | `"step-ca"` | systemd unit restarted after the provisioner changes. |
| `openvpn_stepca_cert_duration` | str | `"8760h"` | Validity of the issued certificates; also the maximum and default duration of the provisioner. |
| `openvpn_stepca_server_name` | str | `"openvpn-server"` | Common name of the server certificate. |

### Clients

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_clients` | list | `[]` | Clients to create. Each gets a certificate, an optional static address and a profile. |
| `openvpn_clients_dir` | path | `"/etc/openvpn/clients"` | Directory on the server holding the client profiles. |
| `openvpn_server_public_address` | str | `"{{ ansible_host \| default(inventory_hostname) }}"` | Address or name clients connect to, written in the profiles. |
| `openvpn_clients_extra_config` | list | `[]` | Raw directives appended to every client profile, one per entry. |
| `openvpn_clients_export_enabled` | bool | `true` | Fetch the profiles to the controller. |
| `openvpn_clients_export_dir` | path | `"{{ inventory_dir | dirname }}/exports/openvpn-clients"` | Controller directory receiving the profiles. They embed the client keys: protect or encrypt this directory. |

### VPN DNS resolver

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_dns_enabled` | bool | `true` | Run a dedicated dnsmasq instance bound to the VPN address. |
| `openvpn_dns_package` | str | `"dnsmasq"` | Package providing dnsmasq. |
| `openvpn_dns_binary` | path | `"/usr/sbin/dnsmasq"` | Path of the dnsmasq executable. |
| `openvpn_dns_service_name` | str | `"dnsmasq-vpn"` | Name of the systemd unit of the VPN resolver. |
| `openvpn_dns_config_file` | path | `"/etc/dnsmasq-vpn.conf"` | Configuration file of the VPN resolver. |
| `openvpn_dns_config_dir` | path | `"/etc/dnsmasq-vpn.d"` | Directory of additional configuration files of the VPN resolver. |
| `openvpn_dns_listen_address` | str | `"10.8.0.1"` | VPN address the resolver listens on. |
| `openvpn_dns_port` | int | `53` | Port the resolver listens on. |
| `openvpn_dns_upstream_servers` | list | `[1.1.1.1, 1.0.0.1]` | Upstream resolvers. |
| `openvpn_dns_local_domain` | str | `"vpn.internal"` | Local domain of the VPN. Each client is served as <name>.<domain>. |
| `openvpn_dns_hosts` | list | `[]` | Additional names served by the VPN resolver. |
| `openvpn_dns_cache_size` | int | `500` | Resolver cache size. |
| `openvpn_dns_publish_to_main` | bool | `false` | Also write the client records into the configuration directory of the main dnsmasq instance and restart it. |
| `openvpn_dns_main_config_dir` | path | `"/etc/dnsmasq.d"` | Configuration directory of the main dnsmasq instance. |
| `openvpn_dns_main_service_name` | str | `"dnsmasq"` | systemd unit of the main dnsmasq instance. |

### step-ca on the VPN

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `openvpn_stepca_nginx_enabled` | bool | `false` | Publish step-ca on the VPN address through nginx and name it in the VPN resolver. nginx must be installed and the proxy certificate must exist (see the step_ca role). |
| `openvpn_stepca_domain` | str | `"{{ step_ca_domain \| default('step-ca.internal') }}"` | Name under which step-ca is published. Follows the step_ca role when it ran in the same play. |
| `openvpn_stepca_upstream` | str | `"127.0.0.1:8443"` | host:port of the authority behind the proxy. |
| `openvpn_stepca_nginx_binary` | path | `"/usr/sbin/nginx"` | Path of nginx, used to detect an installation. |
| `openvpn_stepca_nginx_service_name` | str | `"nginx"` | systemd unit reloaded after a change. |
| `openvpn_stepca_nginx_sites_available` | path | `"/etc/nginx/sites-available"` | nginx sites-available directory. |
| `openvpn_stepca_nginx_sites_enabled` | path | `"/etc/nginx/sites-enabled"` | nginx sites-enabled directory. |
| `openvpn_stepca_nginx_cert_dir` | path | `"/etc/letsencrypt/live/{{ openvpn_stepca_domain }}"` | Directory holding fullchain.pem and privkey.pem of the proxy certificate. |
| `openvpn_stepca_nginx_ssl_protocols` | str | `"TLSv1.2 TLSv1.3"` | ssl_protocols of the proxy. |
| `openvpn_stepca_nginx_ssl_ciphers` | str | `"ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384"` | ssl_ciphers of the proxy. |


## Handlers

| Topic | Effect |
| --- | --- |
| `openvpn \| restart` | Restarts the server (only when `openvpn_service_state` is `started`). |
| `openvpn \| reload systemd` | Runs `systemctl daemon-reload`. |
| `openvpn \| restart dnsmasq vpn` | Restarts the VPN resolver unit. |
| `openvpn \| restart dnsmasq` | Restarts the main dnsmasq instance (client records published to it). |
| `openvpn \| restart step-ca` | Restarts step-ca after its provisioner changed. |
| `openvpn \| reload nginx` | Reloads nginx after the step-ca site changed. |
| `openvpn \| save iptables` | Runs `iptables-save` into `openvpn_firewall_rules_file` when `openvpn_firewall_persist` is true. |

## Verification status

The role is checked with `ansible-playbook --syntax-check`, the argument
specification is validated against the defaults, all templates are rendered
locally with sample clients, and the client name validation and the netmask to
prefix computation were exercised. It has not been run against a live host:
package installation, Easy-RSA and step-ca certificate issuance, the
`ca.json` provisioner edit, the iptables rule, the services and the generated
profiles with a real client are untested.
