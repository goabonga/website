Feature: Nginx configuration rendering
  Each domain gets an nginx virtual host rendered from Jinja2 templates: first a
  plain HTTP one that answers the ACME challenge, then the full HTTPS one once a
  certificate exists. Nothing is written to disk: the scenarios only render
  configurations and inspect the commands the manager would run.

  Scenario: The default HTTP configuration serves the ACME challenge
    Given a domain "shop.example.com" proxied to "/run/shop.sock"
    When I render the default HTTP configuration
    Then the configuration contains "server_name shop.example.com;"
    And the configuration contains "location /.well-known/acme-challenge/"
    And the configuration contains "return 301 https://$host$request_uri;"

  Scenario: The default HTTPS configuration proxies to the upstream socket
    Given a domain "shop.example.com" proxied to "/run/shop.sock"
    When I render the default HTTPS configuration
    Then the configuration contains "server unix:/run/shop.sock;"
    And the configuration contains "ssl_certificate /srv/letsencrypt/live/shop.example.com/fullchain.pem;"
    And the configuration contains "listen 443 ssl"

  Scenario: A custom template replaces the default one
    Given a domain "shop.example.com" proxied to "/run/shop.sock"
    And a custom HTTP template "server { server_name {{ domain }}; return 204; }"
    When I render the configuration with the custom template
    Then the configuration contains "server_name shop.example.com;"
    And the configuration contains "return 204;"

  Scenario: A template with a syntax error is reported with its line
    When I check the template "line one\n{% if %}\nline three"
    Then the template is invalid
    And the template error mentions "line 2"

  Scenario: A valid template is rendered with test variables
    When I render the template "server_name {{ domain }};" for domain "check.example.com"
    Then the template is valid
    And the rendered template is "server_name check.example.com;"

  Scenario: A configuration is installed by the privileged helper
    Given a domain "shop.example.com" proxied to "/run/shop.sock"
    And the system commands are recorded instead of executed
    When I write the configuration for the domain
    Then the recorded command is "sudo -n /opt/custom-domain/privileged-helper --sites-dir /srv/nginx-sites --config-prefix custom-domain- --staging-dir <staging> write-config shop.example.com"
    And the staging directory is empty

  Scenario: A configuration is removed by the privileged helper
    Given the system commands are recorded instead of executed
    When I remove the configuration of "shop.example.com"
    Then the recorded command is "sudo -n /opt/custom-domain/privileged-helper --sites-dir /srv/nginx-sites --config-prefix custom-domain- remove-config shop.example.com"

  Scenario: Reloading nginx tests the configuration first
    Given the system commands are recorded instead of executed
    When I reload nginx
    Then the recorded commands are
      """
      sudo -n /opt/custom-domain/privileged-helper --nginx-bin /opt/nginx/sbin/nginx test-nginx
      sudo -n /opt/custom-domain/privileged-helper --systemctl-bin /opt/systemd/systemctl --nginx-service nginx reload-nginx
      """

  Scenario: The sudoers rules are generated from the same commands
    When I list the sudoers rules for user "worker"
    Then the sudoers rules include "worker ALL=(root) NOPASSWD: /opt/custom-domain/privileged-helper --nginx-bin /opt/nginx/sbin/nginx test-nginx"
    And the sudoers rule for "write-config" ends with a wildcard for the domain
