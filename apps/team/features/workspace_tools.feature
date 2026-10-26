Feature: Workspace tools
  Agents work in a workspace directory: they read and write files, use git,
  talk to GitHub and query the database in read-only mode. The workspace is a
  temporary directory in the scenarios, the git remote is a local bare
  repository and GitHub is played by an in-memory HTTP transport.

  Background:
    Given I am authenticated with the scopes "team:platform:read team:platform:write"
    And I send a POST request to "/platform/team" with the JSON '{"name": "Engineering", "slug": "engineering"}'
    And I remember the response field "id" as "team_id"
    And I send a POST request to "/platform/${team_id}/agents" with the JSON '{"name": "DevAgent", "role": "developer"}'
    And I remember the response field "id" as "agent_id"
    And an empty workspace

  Scenario: Writing, reading and deleting a file
    When the agent runs the tool "file_write" with '{"path": "notes/todo.md", "content": "- ship it"}' in the workspace
    Then the tool result field "written" is "True"
    And the workspace contains the file "notes/todo.md"
    When the agent runs the tool "file_read" with '{"path": "notes/todo.md"}' in the workspace
    Then the tool result field "content" is "- ship it"
    When the agent runs the tool "file_delete" with '{"path": "notes/todo.md"}' in the workspace
    Then the tool result field "deleted" is "True"
    And the workspace does not contain the file "notes/todo.md"

  Scenario: A path cannot leave the workspace
    When the agent runs the tool "file_read" with '{"path": "../outside.txt"}' in the workspace
    Then the tool result field "error" is "Path traversal blocked: ../outside.txt"
    When the agent runs the tool "file_write" with '{"path": "../../etc/evil", "content": "x"}' in the workspace
    Then the tool result field "error" is "Path traversal blocked: ../../etc/evil"

  Scenario: Reading a missing or oversized file
    When the agent runs the tool "file_read" with '{"path": "missing.txt"}' in the workspace
    Then the tool result field "error" is "File not found: missing.txt"
    Given a file "big.txt" of 102401 bytes in the workspace
    When the agent runs the tool "file_read" with '{"path": "big.txt"}' in the workspace
    Then the tool result field "error" is "File too large (max 102400 bytes)"

  Scenario: Managing directories
    When the agent runs the tool "dir_mkdir" with '{"path": "src/app"}' in the workspace
    Then the tool result field "created" is "True"
    When the agent runs the tool "file_write" with '{"path": "src/app/main.py", "content": "print(1)"}' in the workspace
    And the agent runs the tool "dir_list" with '{"path": "src"}' in the workspace
    Then the tool result field "entries.0.name" is "app"
    And the tool result field "entries.0.type" is "directory"
    When the agent runs the tool "dir_rmdir" with '{"path": "src"}' in the workspace
    Then the tool result field "error" is "Directory not empty: src. Use recursive=true to remove."
    When the agent runs the tool "dir_rmdir" with '{"path": "src", "recursive": true}' in the workspace
    Then the tool result field "removed" is "True"
    And the workspace does not contain the file "src/app/main.py"

  Scenario: A change is reviewed, committed and pushed
    Given a git repository "repo" in the workspace with a pushed file "README.md"
    When the agent runs the tool "file_write" with '{"path": "repo/README.md", "content": "changed"}' in the workspace
    And the agent runs the tool "git_diff" with '{"directory": "repo"}' in the workspace
    Then the tool result field "diff" contains "=== Unstaged ==="
    When the agent runs the tool "git_commit_push" with '{"directory": "repo", "message": "Change the readme", "branch": "main"}' in the workspace
    Then the tool result field "pushed" is "True"
    And the remote repository has 2 commits on "main"
    When the agent runs the tool "git_diff" with '{"directory": "repo"}' in the workspace
    Then the tool result field "diff" is "(no changes)"

  Scenario: Creating a branch
    Given a git repository "repo" in the workspace with a pushed file "README.md"
    When the agent runs the tool "git_create_branch" with '{"directory": "repo", "branch": "feature/docs"}' in the workspace
    Then the tool result field "branch" is "feature/docs"

  Scenario: Git tools explain what is missing
    When the agent runs the tool "git_diff" with '{"directory": "nowhere"}' in the workspace
    Then the tool result field "error" is "Directory not found: nowhere"
    When the agent runs the tool "git_clone" with '{"repo": "app"}' in the workspace
    Then the tool result field "error" is "GitHub token or owner not configured"

  Scenario: Creating an issue on GitHub
    Given the services answer '{"number": 7, "html_url": "https://github.com/example/app/issues/7"}' with the status 201
    When the agent runs the tool "github_create_issue" with '{"repo": "app", "title": "Bug", "body": "It fails", "labels": ["bug"]}' and the credentials '{"github_token": "gh-token", "github_owner": "example"}'
    Then the tool result field "issue_number" is "7"
    And the services received a POST request on "/repos/example/app/issues"
    And the services received the bearer token "gh-token"
    And the services received the JSON body '{"title": "Bug", "body": "It fails", "labels": ["bug"]}'

  Scenario: Opening a pull request on another owner's repository
    Given the services answer '{"number": 12, "html_url": "https://github.com/other/lib/pull/12"}' with the status 201
    When the agent runs the tool "github_create_pr" with '{"repo": "other/lib", "title": "Fix", "head": "fix-1"}' and the credentials '{"github_token": "gh-token", "github_owner": "example"}'
    Then the tool result field "pr_number" is "12"
    And the services received a POST request on "/repos/other/lib/pulls"
    And the services received the JSON body '{"title": "Fix", "head": "fix-1", "base": "main"}'

  Scenario: Commenting and listing the CI runs
    Given the services answer '{"id": 99, "html_url": "https://github.com/example/app/issues/7#c99"}' with the status 201
    When the agent runs the tool "github_comment" with '{"repo": "app", "issue_number": 7, "body": "On it"}' and the credentials '{"github_token": "gh-token", "github_owner": "example"}'
    Then the tool result field "comment_id" is "99"
    And the services received a POST request on "/repos/example/app/issues/7/comments"
    Given the services answer '{"total_count": 1, "workflow_runs": [{"id": 5, "name": "CI", "status": "completed", "conclusion": "success", "head_branch": "main", "head_sha": "0123456789abcdef", "html_url": "https://github.com/example/app/actions/runs/5", "created_at": "2026-03-01T10:00:00Z"}]}' with the status 200
    When the agent runs the tool "github_list_runs" with '{"repo": "app", "branch": "main"}' and the credentials '{"github_token": "gh-token", "github_owner": "example"}'
    Then the tool result field "runs.0.conclusion" is "success"
    And the tool result field "runs.0.commit_sha" is "01234567"
    And the services received the query "per_page=5&branch=main"

  Scenario: GitHub errors are returned to the agent
    Given the services answer 'Not Found' with the status 404
    When the agent runs the tool "github_create_issue" with '{"repo": "missing", "title": "Bug"}' and the credentials '{"github_token": "gh-token", "github_owner": "example"}'
    Then the tool result field "error" is "GitHub API error 404: Not Found"

  Scenario: GitHub tools need a token and an owner
    When the agent runs the tool "github_create_issue" with '{"repo": "app", "title": "Bug"}'
    Then the tool result field "error" is "GitHub token or owner not configured"

  Scenario: Only read-only queries are executed
    When the agent runs the tool "postgres_query" with '{"query": "DELETE FROM tasks"}'
    Then the tool result field "error" is "Only SELECT queries are allowed"
    When the agent runs the tool "postgres_query" with '{"query": "SELECT 1; DROP TABLE tasks"}'
    Then the tool result field "error" is "Query contains forbidden keywords"

  Scenario: A read-only query returns its rows
    Given the database answers the rows '[{"id": 1, "title": "Review"}, {"id": 2, "title": "Deploy"}]'
    When the agent runs the tool "postgres_query" with '{"query": "SELECT id, title FROM tasks;"}'
    Then the tool result field "count" is "2"
    And the tool result field "truncated" is "False"
    And the tool result field "rows.1.title" is "Deploy"
    And the database received the connection string "postgresql://team:team@localhost:5432/team"
