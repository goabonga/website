# Seed data

A new installation does not start empty: the migrations insert the GOABONGA
startup team, its agents, the tools they may use and their skills. This is what
makes the periodic jobs useful right after the first migration: the auto
orchestration of [Task dispatch](16-task-dispatch.md) looks for the team whose
slug is `goabonga` and for its `ceo` agent. This feature adds five data
revisions after the schema revisions of the previous features.

## Revisions

| Revision | What it does |
|----------|--------------|
| `0008_seed_goabonga_team` | Inserts the team `GOABONGA` (slug `goabonga`, `config.orchestration = {"enabled": true, "schedule_minutes": 15}`) and its 19 agents |
| `0009_add_save_memory_tool` | Adds `save_memory` to the tools of every agent that has a tool list and not yet that tool |
| `0010_add_github_crud_tools` | Adds the read and update GitHub tools and `git_create_branch`/`git_diff` next to the tool that justifies them (for example `github_get_issue` and `github_update_issue` next to `github_create_issue`, `git_create_branch` next to `git_clone`) |
| `0011_add_memory_crud_tools` | Adds `update_memory` and `delete_memory` to the agents that have `save_memory` |
| `0012_seed_goabonga_skills` | Inserts three or four skills for each of the 19 agents |

The downgrades undo them: the team and its agents are deleted, the added tools
are removed from the tool lists, the skills of the team are deleted.

## The agents

Each agent has a role (unique in the team), a system prompt, a provider and
model, and a `config` with its `tools` and its `max_iterations`:

| Role | Provider |
|------|----------|
| `cto`, `developer`, `devops`, `qa`, `security`, `ceo`, `legal` | Anthropic (`claude-sonnet-4-5-20250929`) |
| `frontend`, `product_manager`, `designer`, `data_analyst`, `marketing`, `sales`, `cfo`, `support`, `tech_writer`, `hr`, `community`, `scrum_master` | OpenAI (`gpt-4o`) |

The tools of an agent follow its job: the developers have the file, git, GitHub
and database tools, the business roles have the billing, mailler, analytics and
auth tools, the CEO and the scrum master have `team_status`, and so on. Every
tool named by the seed is registered, and every tool added by the later
revisions too (the tests check it). The skills of a role are named after its
work, for example `architecture-review` for the CTO or `incident-response` for
the DevOps engineer.

The credentials in `config.credentials` are empty: the GitHub token and the
service URLs come from the settings of the application (see
[Workspace tools](13-workspace-tools.md) and [Service tools](12-service-tools.md)).

## Existing databases

The standalone application used the revision ids `001` to `008` for the same
schema and data. The history was re-split by feature (see [Teams](03-teams.md)),
so a database that was migrated with the old ids has the same tables, the same
rows and a revision id (`008`) that the new history does not know. Do not run
`upgrade head` on it, which would try to create the tables again or fail on the
unknown revision; stamp it once instead:

```bash
uv run --package team alembic -c apps/team/alembic.ini stamp head
```

A new database is migrated normally with `upgrade head`.

## Settings

No new setting. The seeded team is the one the beat schedule targets
(`team_slug` of the auto orchestration).

## Tests

pytest: `tests/test_seed_migrations.py` loads the revisions and runs them
against a recording connection: the inserts of the team, the agents and the
skills, the downgrades, the registration of every tool named by the seed, the
validity of every skill against the skill schema, and the skip of missing teams
and agents; `tests/test_migrations.py` still renders the schema revisions
offline and now ignores the data revisions.

behave (`features/seed_data.feature`):

- The seed creates the GOABONGA team
- The seed creates one agent per role
- Every tool of the seeded agents exists
- The tools added by later revisions follow the tool that justifies them
- The seeded team can be orchestrated by its CEO (the seeded rows are loaded in
  the in-memory database and the auto orchestration runs on them)
- The seed adds skills to every agent
- Skills are skipped for a missing team or agent
- Downgrading removes what was seeded

The SQL of the tool revisions (`jsonb_set`) is PostgreSQL specific and is not
executed by the tests.
