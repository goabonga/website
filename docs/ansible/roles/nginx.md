# nginx

Install nginx with a hardened global configuration, default and hostname virtual hosts, error pages and optional HTTPS.

Installs nginx, renders nginx.conf and a catch-all default virtual host, optionally a virtual host for a host name, custom HTML error pages and, through certbot, a Let's Encrypt certificate that upgrades the host name virtual host to HTTPS.

## Requirements

- Debian 12 or 13, Ubuntu 22.04 or 24.04.
- Privilege escalation (`become: true`).
- `certbot` available on the host when `nginx_https_enabled` is true (install it with the `certbot` role).

## Variables

Every variable is optional and defined in `defaults/main.yml`. The role validates them against `meta/argument_specs.yml` before running.

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `nginx_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `nginx_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages. |
| `nginx_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### Installation and service

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `nginx_packages` | list of str | `["nginx"]` | Packages to install. |
| `nginx_service_name` | str | `"nginx"` | systemd unit name. |
| `nginx_service_state` | str | `"started"` | State of the service after configuration. Choices: `started`, `stopped`. |
| `nginx_service_enabled` | bool | `true` | Enable the service at boot. |
| `nginx_user` | str | `"www-data"` | User the worker processes run as, also owner of the web roots. |
| `nginx_group` | str | `"www-data"` | Group owning the web roots. |
| `nginx_config_dir` | path | `"/etc/nginx"` | Nginx configuration directory. |
| `nginx_log_dir` | path | `"/var/log/nginx"` | Directory of the access and error logs. |
| `nginx_root` | path | `"/var/www/html"` | Document root: the default and hostname pages, the error pages and the ACME webroot live below it. |
| `nginx_test_config` | bool | `true` | Validate the configuration with nginx -t before starting the service. |
| `nginx_remove_distribution_site` | bool | `true` | Remove the distribution default site from sites-enabled. |

### Global configuration

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `nginx_worker_processes` | str | `"auto"` | Value of worker_processes (auto or a number). |
| `nginx_worker_connections` | int | `1024` | Maximum connections per worker. |
| `nginx_multi_accept` | bool | `true` | Let a worker accept all new connections at once. |
| `nginx_server_tokens` | bool | `false` | Show the nginx version in responses and error pages. |
| `nginx_keepalive_timeout` | int | `65` | Keep-alive timeout in seconds. |
| `nginx_client_max_body_size` | str | `"1m"` | Maximum accepted request body size. |
| `nginx_error_log_level` | str | `"error"` | Severity of the error log. Choices: `debug`, `info`, `notice`, `warn`, `error`, `crit`, `alert`, `emerg`. |
| `nginx_gzip_enabled` | bool | `true` | Compress text responses. |
| `nginx_gzip_comp_level` | int | `6` | Gzip compression level (1 to 9). |
| `nginx_gzip_types` | list of str | `["text/plain", "text/css", "text/xml", "application/json", "application/javascript", "application/rss+xml", "application/atom+xml", "image/svg+xml"]` | MIME types compressed in addition to text/html. |
| `nginx_extra_http_config` | list of str | `[]` | Raw lines added to the http block of nginx.conf. |

### TLS

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `nginx_ssl_protocols` | list of str | `["TLSv1.2", "TLSv1.3"]` | Accepted TLS protocol versions. |
| `nginx_ssl_ciphers` | str | `"ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384"` | TLS cipher list of the HTTPS virtual host. |
| `nginx_ssl_session_cache` | str | `"shared:SSL:10m"` | TLS session cache. |
| `nginx_ssl_session_timeout` | str | `"1d"` | TLS session lifetime. |
| `nginx_hsts_enabled` | bool | `false` | Send the Strict-Transport-Security header on the HTTPS virtual host. |
| `nginx_hsts_max_age` | int | `31536000` | max-age of the HSTS header in seconds. |

### Default virtual host

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `nginx_default_vhost_enabled` | bool | `true` | Deploy the catch-all default virtual host. |
| `nginx_default_vhost_name` | str | `"999-default"` | File name of the default virtual host. It must sort last so the catch-all never wins over a named host. |
| `nginx_listen_ipv4` | str | `""` | IPv4 address to listen on. Every IPv4 address when empty. |
| `nginx_listen_ipv6` | str | `""` | IPv6 address to listen on. Every IPv6 address when empty. |
| `nginx_ipv6_enabled` | bool | `true` | Add IPv6 listen directives. |
| `nginx_default_page_enabled` | bool | `true` | Write a landing page for the default virtual host. |
| `nginx_default_page_title` | str | `""` | Heading of the default landing page. The inventory host name is used when empty. |
| `nginx_default_page_message` | str | `"Server is running"` | Text of the landing pages. |
| `nginx_redirect_ip_to_hostname` | bool | `false` | Answer requests that do not match a host name with a 301 redirect to nginx_hostname instead of the landing page. |
| `nginx_default_vhost_extra_config` | list of str | `[]` | Raw lines added to the server block of the default virtual host. |

### Hostname virtual host

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `nginx_hostname` | str | `""` | Host name served by the hostname virtual host. The virtual host is not created when empty. |
| `nginx_hostname_vhost_enabled` | bool | `true` | Deploy the hostname virtual host when nginx_hostname is set. |
| `nginx_hostname_vhost_extra_config` | list of str | `[]` | Raw lines added to the server blocks of the hostname virtual host. |
| `nginx_acme_webroot` | path | `"/var/www/html"` | Directory served at /.well-known/acme-challenge/ by the hostname virtual host. It must match the certbot webroot. |

### HTTPS certificate

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `nginx_https_enabled` | bool | `false` | Obtain a certificate for nginx_hostname with certbot and serve the host over HTTPS. |
| `nginx_https_redirect` | bool | `true` | Redirect HTTP to HTTPS once a certificate exists. |
| `nginx_certbot_email` | str | `""` | Account e-mail used to obtain the certificate. Required when nginx_https_enabled is true. |
| `nginx_certbot_agree_tos` | bool | `false` | Accept the certificate authority terms of service. Must be true when nginx_https_enabled is true. |
| `nginx_certbot_staging` | bool | `false` | Use the staging environment of the certificate authority. |
| `nginx_certbot_extra_args` | list of str | `[]` | Additional certbot command line arguments. |
| `nginx_letsencrypt_dir` | path | `"/etc/letsencrypt"` | Certbot configuration directory holding the live certificates. |

### Error pages

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `nginx_error_pages_enabled` | bool | `true` | Deploy the custom HTML error pages. |
| `nginx_error_pages` | list of dict | `[{"code": 403, "title": "Forbidden", "message": "You don't have permission to access this resource.", "icon": "&#x1F6AB;"}, {"code": 404, "title": "Not Found", "message": "The page you're looking for doesn't exist or has been moved.", "icon": "&#x1F50D;"}, {"code": 500, "title": "Internal Server Error", "message": "Something went wrong on our end. Please try again later.", "icon": "&#x1F525;"}, {"code": 502, "title": "Bad Gateway", "message": "The server is temporarily unable to handle your request. Please try again in a moment.", "icon": "&#x1F6A7;"}, {"code": 503, "title": "Service Unavailable", "message": "We're currently performing maintenance. Please check back shortly.", "icon": "&#x1F527;"}, {"code": 504, "title": "Gateway Timeout", "message": "The server took too long to respond. Please try again later.", "icon": "&#x23F3;"}]` | Error pages to deploy. |

Keys of each `nginx_error_pages` item:

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `code` | int | yes | HTTP status code. |
| `title` | str | yes | Page heading. |
| `message` | str | yes | Explanation shown to the visitor. |
| `icon` | str | yes | HTML entity or emoji displayed above the code. |

## Behavior

- `nginx.conf` is validated with `nginx -t -c` before being installed, and the full configuration is tested again before the service is started.
- The default virtual host is a catch-all (`default_server`). Its file name sorts last so it never wins over a named host. It serves a landing page, or redirects to `nginx_hostname` when `nginx_redirect_ip_to_hostname` is true.
- The hostname virtual host exists only when `nginx_hostname` is set. Its port 80 server always answers ACME challenges from `nginx_acme_webroot`, so certificate renewals keep working after the HTTPS upgrade.
- With `nginx_https_enabled`, the role first serves the host over HTTP, requests the certificate with `certbot certonly --webroot`, then renders the HTTPS server and reloads nginx. A certificate that already exists is reused.
- `nginx_listen_ipv4` and `nginx_listen_ipv6` restrict the listen directives to one address each; empty values listen on every address.
- The error pages are rendered from the `nginx_error_pages` list and shared through the `snippets/error-pages.conf` file, which a virtual host written outside this role can include.
- The role does not configure fail2ban; set `fail2ban_nginx_enabled: true` in the `fail2ban` role to protect the logs written here.

## Tags

| Tag | Scope |
| --- | --- |
| `nginx` | Every task of the role. |

## Example

```yaml
- hosts: web
  become: true
  roles:
    - role: goabonga.website.certbot
    - role: goabonga.website.nginx
      vars:
        nginx_hostname: www.example.com
        nginx_redirect_ip_to_hostname: true
        nginx_https_enabled: true
        nginx_certbot_email: ops@example.com
        nginx_certbot_agree_tos: true
        nginx_hsts_enabled: true
```

## See also

- `certbot` role: renewal timer and hooks.
- `fail2ban` role: nginx jails.
