# goabonga.website

Ansible collection that provisions hosts and deploys the website platform
applications.

- **Roles** for the base infrastructure: `users`, `security`, `common`,
  `dnsmasq`, `redis`, `postgres`, `step_ca`, `step_ca_client`, `geoip`,
  `certbot`, `nginx`, `fail2ban`, `openvpn`, `openvpn_client`, `asterisk` and
  `protonmail_bridge`.
- **`python_app`**, which deploys the applications of this repository from the
  monorepo (uv virtualenv, encrypted credentials, systemd units), driven by a
  catalog of components.
- **Playbooks** `bootstrap`, `site` and `apps` in `playbooks/`.
- **An example project** in `examples/` to copy as the start of an
  infrastructure repository.

The collection is installed from Git, not from Ansible Galaxy:

```yaml
collections:
  - name: https://github.com/goabonga/website.git#/ansible/
    type: git
    version: main
```

The documentation is in `docs/ansible/` of the repository.
