# Command line

The `mailler` command administers the service straight from the database, for
the operators who deploy a new application and for provisioning scripts. It
reads the same settings as the application (`DATABASE_URL`) and applies the
same validation as the API; it needs no token. It is installed with the
package (`[project.scripts]`) and can also be run as `python -m mailler.cli`.

```bash
mailler --help
```

Exit codes: `0` on success, `1` for an error (unknown client, compilation
failure, ...), `2` for invalid input.

## Clients

| Command | Description |
| --- | --- |
| `mailler clients list [--inactive]` | One line per client: id, `active`/`inactive`, default sender, default provider |
| `mailler clients show CLIENT_ID` | The record as JSON |
| `mailler clients register CLIENT_ID [options]` | Register a client; refused when it already exists |
| `mailler clients update CLIENT_ID [options]` | Change only the given options |
| `mailler clients activate CLIENT_ID` | Accept the client again |
| `mailler clients deactivate CLIENT_ID` | Refuse the client (see [authorized clients](15-authorized-clients.md)) |

Options of `register` and `update` (`register` also takes `--inactive`):

| Option | Field |
| --- | --- |
| `--name` | Display name |
| `--from-email`, `--from-name` | Default sender identity |
| `--reply-to` | Fixed reply-to address |
| `--allowed-sender EMAIL[=NAME]` | Another sender identity; repeat the option for several |
| `--allowed-provider PROVIDER` | Allowed provider; repeat the option for several |
| `--default-provider` | Provider used when a request names none |
| `--rate-limit-per-minute N`, `--daily-quota N` | [Sending limits](16-client-limits.md); `0` removes a limit |

On `update`, `--allowed-sender` and `--allowed-provider` replace the whole
list and an empty value (`--reply-to ""`) clears an optional field.

## Templates

Clients upload their own MJML templates through the template API
([MJML templates](08-templates.md)); the command imports a whole set at once,
which is how an application provisions its templates when it is deployed.
Mailler contains no template of any application.

```bash
mailler templates import --client-id my-application ./templates
mailler templates list --client-id my-application
```

The directory holds, for each template, `<slug>.mjml` (the source) and
`<slug>.json` (its description). The file name is the slug of the template.
The description accepts `subject_template` (required), `name` (the slug by
default), `description`, `plain_text`, `variables`, `metadata` and `status`;
any other key is refused.

```json
{
  "name": "Workspace invitation",
  "subject_template": "{{ inviter }} invites you to {{ workspace }}",
  "plain_text": "Join %workspace%: %link%"
}
```

- The import is idempotent: a template that exists for the client is updated,
  the others are created. Templates never cross clients.
- Imported templates are `active` (what [sending from a template](18-template-sending.md)
  requires), unless the description or `--status` says otherwise.
- Every source is compiled first; if one fails nothing is written.
  `--dry-run` validates and compiles without writing.

## How it is tested

- pytest: `tests/test_cli.py` runs every command against a temporary SQLite
  database (registration, validation, listing, updates, clearing fields,
  activation, template import with the real MJML compiler, idempotence, client
  isolation, dry run, file checks) and checks the `mailler` entry point.
- behave: `features/cli.feature` runs the command in the scenario database and
  follows up through the API (a client registered from the command line can
  send, a deactivated one is refused, imported templates are readable by their
  client only).
