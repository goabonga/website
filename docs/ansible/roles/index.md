# Roles

Every role has its own page with the variables, the behavior and an example.
The roles are used through the three [playbooks](../06-playbooks.md), or on
their own as `goabonga.website.<role>`.

| Role | Purpose |
| --- | --- |
| [users](users.md) | Deploy user and additional accounts with SSH keys and sudo rules. |
| [security](security.md) | SSH hardening, optional ufw firewall and unattended upgrades. |
| [common](common.md) | Packages, time zone, locale, bash prompt and tmux. |
| [dnsmasq](dnsmasq.md) | Local caching DNS resolver with custom records. |
| [redis](redis.md) | Redis server. |
| [postgres](postgres.md) | PostgreSQL server, roles, databases and extensions. |
| [step_ca](step_ca.md) | Private certificate authority. |
| [step_ca_client](step_ca_client.md) | Trust the private CA and point certbot at it. |
| [geoip](geoip.md) | MaxMind GeoLite2 databases. |
| [certbot](certbot.md) | Let's Encrypt certificates and renewal. |
| [nginx](nginx.md) | Web server with a hardened configuration and optional HTTPS. |
| [fail2ban](fail2ban.md) | Intrusion banning with SSH, nginx and Asterisk jails. |
| [openvpn](openvpn.md) | OpenVPN server with its PKI and VPN resolver. |
| [openvpn_client](openvpn_client.md) | OpenVPN client profile. |
| [asterisk](asterisk.md) | Asterisk with a SIP trunk and dialplan. |
| [protonmail_bridge](protonmail_bridge.md) | Proton Mail Bridge as a headless service. |
| [python_app](python_app.md) | The platform applications, deployed from the monorepo. |
