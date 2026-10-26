Feature: Command line interface
  The custom-domain command seeds the database and manages authorized clients without going
  through the API. The commands run in-process on an in-memory database.

  Scenario: Seeding creates the default nginx template
    When I run the command "seed"
    Then the command succeeds
    And the output contains "Created default nginx template"
    And the default template exists with the packaged HTTP and HTTPS sources

  Scenario: Seeding twice does not duplicate the template
    Given I ran the command "seed"
    When I run the command "seed"
    Then the command succeeds
    And the output contains "Default template already exists"
    And there is 1 template in the database

  Scenario: Creating an authorized client
    When I run the command "create-client --client-id tenant-a --name 'Tenant A' --upstream /run/a.sock --cname apps.example.com --max-domains 3"
    Then the command succeeds
    And the output contains "Created client: tenant-a"
    And the client "tenant-a" is stored with 3 maximum domains

  Scenario: Creating the same client twice fails
    Given I ran the command "create-client --client-id tenant-a --name 'Tenant A'"
    When I run the command "create-client --client-id tenant-a --name 'Tenant A'"
    Then the command fails
    And the output contains "Client already exists: tenant-a"

  Scenario: Listing clients
    Given I ran the command "create-client --client-id tenant-a --name 'Tenant A' --cname apps.example.com"
    When I run the command "list-clients"
    Then the output contains "tenant-a (Tenant A) - active"
    And the output contains "CNAME: apps.example.com"

  Scenario: Listing templates
    Given I ran the command "seed"
    When I run the command "list-templates"
    Then the output contains "Default Template (DEFAULT) - active"

  Scenario: Listing when nothing exists
    When I run the command "list-clients"
    Then the output contains "No clients found"

  Scenario: Printing the sudoers rules for the worker
    When I run the command "sudoers --user worker"
    Then the command succeeds
    And the output contains "worker ALL=(root) NOPASSWD: /opt/custom-domain/privileged-helper --nginx-bin /opt/nginx/sbin/nginx test-nginx"
    And the output contains "certbot-issue *"
