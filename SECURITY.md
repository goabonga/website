# Security Policy

## Supported versions

Security fixes are applied only to the latest released version of each
component (an application, the `ansible` collection or a playbook) on the
`main` branch.

| Version | Supported |
| --- | --- |
| latest release of a component | ✅ |
| older releases | ❌ |

## Reporting a vulnerability

**Please do not open a public issue.** GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
is the preferred channel:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Describe the issue with reproduction steps and a suggested mitigation.

Name the affected component (for example `auth` or `ansible`) in the report.

If you cannot use GitHub's form, email **goabonga@pm.me** with the same
information. PGP encryption is available on request.

You can expect an acknowledgement within **3 business days**, a triage
assessment within **10 business days**, and a fix or written mitigation
plan before any public disclosure.

## Scope

This repository holds the platform services under `apps/` (authentication,
billing, webhooks, VPN portal, APT repository and others) and the Ansible
collection under `ansible/` that provisions hosts and deploys them. The parts
most relevant to security are the authentication and authorization flows, the
handling of untrusted input and provider webhooks, the secrets handling of
the Ansible roles (vault-encrypted credentials, generated keys and
certificates) and the hardening roles (`security`, `fail2ban`, `nginx`,
`openvpn`, `step_ca`).

Vulnerabilities in third-party dependencies should be reported upstream, but
please let us know so the pinned ranges can be bumped.

Thanks for helping keep the project and its users safe.
