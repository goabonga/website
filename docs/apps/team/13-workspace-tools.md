# Workspace tools

Agents work in a workspace: a directory on the host where they read and write
files, clone and commit repositories, and from which they talk to GitHub. This
feature adds the file, git, GitHub and database query tools. They are
registered in the [tool registry](11-tools.md) and return an `{"error": ...}`
object when they cannot do what was asked.

## Files and directories

| Tool | What it does |
|------|--------------|
| `file_read` | Reads a text file of at most 100 KB (`content`, `path`) |
| `file_write` | Writes a file, creating its parent directories |
| `file_delete` | Deletes a file |
| `dir_mkdir` | Creates a directory and its parents |
| `dir_rmdir` | Removes a directory; `recursive=true` is needed when it is not empty |
| `dir_list` | Lists a directory (`entries` with `name` and `type`, `file` or `directory`) |

Every path is relative to the workspace and is resolved against it: a path that
leaves the workspace (for example `../outside`) is refused with `Path traversal
blocked: <path>`. The workspace is the `workspace_dir` of the tool context when
the caller provides one (a directory per task), otherwise the `WORKSPACE_DIR`
setting.

## Git

The git tools run GitPython in a worker thread so that they do not block the
event loop. The `git` executable must be installed on the host.

| Tool | What it does |
|------|--------------|
| `git_clone` | Clones `https://github.com/<owner>/<repo>.git` into the workspace with the GitHub token (`repo`, optional `branch` and `directory`). Needs a token and an owner, and redacts the token from error messages |
| `git_create_branch` | Creates and checks out a branch in a cloned repository, optionally from a `base` branch |
| `git_diff` | Returns the staged and unstaged changes, or `(no changes)` |
| `git_commit_push` | Stages everything, commits with `message` and pushes to `origin` (to `branch` when given) |

## GitHub

All GitHub tools call the REST API with the agent's `config.credentials`
`github_token` and `github_owner`, falling back to the `GITHUB_TOKEN` and
`GITHUB_OWNER` settings; without both they answer `GitHub token or owner not
configured`. A `repo` is either a name, which uses the owner, or `owner/name`,
which targets another owner. A failed call becomes `GitHub API error <status>:
<first 500 characters>`.

| Tool | What it does |
|------|--------------|
| `github_create_issue`, `github_get_issue`, `github_update_issue` | Create, read (title, body, state, labels, assignees, comment count) and update issues; setting the state to `closed` closes one |
| `github_create_pr`, `github_get_pr`, `github_update_pr` | Create, read and update pull requests (the base branch defaults to `main`) |
| `github_comment`, `github_list_comments`, `github_update_comment`, `github_delete_comment` | Manage the comments of an issue or a pull request |
| `github_list_review_comments` | Lists the inline review comments of a pull request |
| `github_list_runs` | Lists the recent GitHub Actions runs, optionally of a branch (at most 10) |
| `github_get_run_logs` | Returns the jobs of a run with their steps and, for each finished job, the first 8000 characters of its log |

## Database queries

`postgres_query` runs one read-only SQL statement against the application
database through `asyncpg`. The statement must start with `SELECT` and must not
contain `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`,
`GRANT` or `REVOKE`, otherwise the tool refuses it. The result holds at most 100
rows (`rows`, `count`, `truncated`). The check is a keyword filter, not a
sandbox: the database role used by the application should itself be limited to
what agents may read.

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKSPACE_DIR` | `<system temp directory>/team-workspace` | Root of the workspace |
| `GITHUB_TOKEN` | empty | Default GitHub token; read as a credential (see [Foundation](01-foundation.md)) |
| `GITHUB_OWNER` | empty | Default GitHub user or organisation |

## Tests

pytest: `tests/test_tools_file_ops.py`, `tests/test_tools_git_ops.py`,
`tests/test_tools_github_ops.py` and `tests/test_tools_postgres_query.py`
cover every tool (success, errors, path traversal, credential resolution,
token redaction), and the registry test lists the new tools.

behave (`features/workspace_tools.feature`), with a temporary workspace, a local
bare repository as git remote, an in-memory HTTP transport for GitHub and a
fake `asyncpg` connection:

- Writing, reading and deleting a file
- A path cannot leave the workspace
- Reading a missing or oversized file
- Managing directories
- A change is reviewed, committed and pushed
- Creating a branch
- Git tools explain what is missing
- Creating an issue on GitHub
- Opening a pull request on another owner's repository
- Commenting and listing the CI runs
- GitHub errors are returned to the agent
- GitHub tools need a token and an owner
- Only read-only queries are executed
- A read-only query returns its rows

`git_clone` itself needs the network and is only covered by pytest with a
mocked clone.
