# Getting started

This page goes from nothing to a host running applications. It uses the
example project shipped in `ansible/examples/` as the starting point of your
own infrastructure repository.

## 1. Prerequisites

- A controller with `ansible-core` 2.16 or later and `git`.
- A host running Debian 12 or 13, or Ubuntu 22.04 or 24.04, reachable over SSH
  with the account the provider created (root or a sudo user).
- A DNS zone you control, with records for the application host names
  (`auth.example.com`, `api.example.com`, ...) pointing to the host.
- An SSH key pair for the deploy account.

## 2. Create the project

Copy the example next to your own files and rename the templates:

```bash
cp -r ansible/examples my-infra
cd my-infra
cp ansible.cfg.example ansible.cfg
cp inventory/hosts.example inventory/hosts
cp inventory/group_vars/all/vault.yml.example inventory/group_vars/all/vault.yml
```

Keep `my-infra` in its own Git repository. The vault password file and any
clear-text secret must never be committed.

## 3. Install the collection

```bash
ansible-galaxy collection install -r requirements.yml
```

`requirements.yml` installs the collection from the `ansible/` directory of
the monorepo. Pin `version` to a release tag of the collection to make runs
reproducible.

## 4. Describe your infrastructure

1. `inventory/hosts`: put the address of the host in the `web` group.
2. `inventory/group_vars/all/main.yml`: set `website_domain`, the deploy
   account's public key, the certbot e-mail address.
3. `inventory/group_vars/all/apps.yml`: choose `website_apps_enabled` and the
   settings that differ from the catalog. See
   [Deploying applications](05-deploying-apps.md).
4. `inventory/group_vars/all/vault.yml`: replace every `CHANGE_ME` (uncomment
   what you enable), then encrypt the file. See [Secrets](03-secrets.md).

```bash
echo 'a-long-random-passphrase' > .vault_pass && chmod 600 .vault_pass
ansible-vault encrypt inventory/group_vars/all/vault.yml
```

Check that the inventory and variables resolve:

```bash
ansible-inventory --list | head
ansible web -m ansible.builtin.debug -a 'var=website_domain'
```

## 5. Bootstrap the host

The first run uses the provider's account and creates the deploy account and
hardens SSH:

```bash
ansible-playbook goabonga.website.bootstrap -e ansible_user=root
```

The `ansible_user` of the example inventory is the deploy account, and an
inventory variable wins over `-u`, hence the extra variable.

The playbook refuses to run when SSH would be hardened without a key for the
deploy account. Afterwards log in as the deploy account to check:

```bash
ssh deploy@203.0.113.10 sudo -n true
```

## 6. Provision the base infrastructure

```bash
ansible-playbook goabonga.website.site
```

This installs the packages, Redis, PostgreSQL, certbot, nginx and fail2ban.
The roles tied to a host role (private CA, VPN, telephony) are enabled per
group; see [Playbooks](06-playbooks.md).

## 7. Deploy the applications

```bash
ansible-playbook goabonga.website.apps
```

Add `--check --diff` to preview a change. The first deployment cannot be fully
previewed: the checkout and the virtualenv do not exist yet.

## 8. Verify

On the host:

```bash
systemctl status backend frontend
journalctl -u backend -n 50
sudo curl -s --unix-socket /run/backend/backend.sock http://localhost/health
```

From anywhere, once DNS and the certificates are in place:

```bash
curl -sI https://api.example.com/ | head -1
```

The health endpoint is reachable from the host only, through the socket or
the loopback address.

## Day-2 operations

| Task | Command |
| --- | --- |
| Deploy one application | `ansible-playbook goabonga.website.apps -e '{"website_apps_limit": ["backend"]}'` |
| Change a setting | edit the variables, run `goabonga.website.apps` |
| Rotate a secret | change it in the vault, run `goabonga.website.apps` |
| Update the infrastructure | `ansible-playbook goabonga.website.site` |
| Update the collection | bump `version` in `requirements.yml`, then `ansible-galaxy collection install -r requirements.yml --force` |
