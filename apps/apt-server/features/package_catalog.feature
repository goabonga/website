Feature: Package catalog and per-package access control
  Uploaded packages are tracked in a database. Each package has an owner, a
  visibility and optional grants to users or groups, and every caller only
  sees the packages the rules allow.

  Background:
    Given a catalog with these packages
      | name   | owner | visibility |
      | pub    | alice | public     |
      | mine   | bob   | private    |
      | secret | alice | private    |
      | shared | alice | shared     |

  @database
  Scenario: Anonymous callers only see public packages
    When an anonymous caller lists the visible packages
    Then the visible packages are "pub"

  @database
  Scenario: Owners also see their own private packages
    When the caller "bob" lists the visible packages
    Then the visible packages are "mine,pub"

  @database
  Scenario: A user grant exposes a shared package
    Given "alice" grants "read" on "shared" to user "bob"
    When the caller "bob" lists the visible packages
    Then the visible packages are "mine,pub,shared"

  @database
  Scenario: A grant to an email address matches the display name of the caller
    Given "alice" grants "read" on "shared" to user "bob@example.com"
    When the user "bob" with mailbox "bob@example.com" lists the visible packages
    Then the visible packages are "mine,pub,shared"

  @database
  Scenario: A group grant exposes a shared package to its members
    Given "alice" grants "read" on "shared" to group "team:ops"
    When the member "carol" of group "team:ops" lists the visible packages
    Then the visible packages are "pub,shared"

  @database
  Scenario: Administrators see every package
    When an administrator lists the visible packages
    Then the visible packages are "mine,pub,secret,shared"

  @database
  Scenario: Only owners and writers may modify a package
    Given "alice" grants "write" on "shared" to user "bob"
    Then caller "bob" can write "shared"
    And caller "bob" cannot write "secret"
    And caller "alice" can write "secret"
    And an anonymous caller cannot write "pub"
