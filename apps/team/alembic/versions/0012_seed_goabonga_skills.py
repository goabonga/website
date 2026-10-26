# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""0012 seed skills for GOABONGA team agents.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-26
"""

import json
import uuid

from alembic import op
from sqlalchemy import text

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

TEAM_SLUG = "goabonga"

# Skills keyed by agent role → list of skill dicts
AGENT_SKILLS: dict[str, list[dict]] = {
    # ── CTO ──────────────────────────────────────────────────────────────
    "cto": [
        {
            "name": "architecture-review",
            "description": "Review a system architecture proposal and provide structured feedback.",
            "content": (
                "# Architecture Review\n\n"
                "## Objective\n"
                "Evaluate a proposed system architecture for scalability, reliability, and maintainability.\n\n"
                "## Steps\n"
                "1. **Understand the scope** — Read the proposal or description provided by the requester.\n"
                "2. **Evaluate components** — For each component, assess:\n"
                "   - Responsibility boundaries (single-responsibility)\n"
                "   - Communication patterns (sync vs async, REST vs events)\n"
                "   - Data ownership and storage strategy\n"
                "3. **Identify risks** — Highlight single points of failure, scalability bottlenecks, "
                "and security concerns.\n"
                "4. **Suggest improvements** — Propose concrete alternatives with trade-off analysis.\n"
                "5. **Summarize** — Write a structured review with sections: Strengths, Risks, Recommendations.\n\n"
                "## Output format\n"
                "Return a markdown document with the review. Create a GitHub issue for each actionable recommendation."
            ),
            "allowed_tools": ["search_memory", "github_create_issue"],
            "metadata": {"category": "engineering", "complexity": "high"},
        },
        {
            "name": "tech-stack-evaluation",
            "description": "Evaluate and compare technology options for a given requirement.",
            "content": (
                "# Tech Stack Evaluation\n\n"
                "## Objective\n"
                "Compare technology options and recommend the best fit for the stated requirement.\n\n"
                "## Steps\n"
                "1. **Clarify requirements** — Identify functional and non-functional needs "
                "(performance, cost, team expertise, ecosystem).\n"
                "2. **List candidates** — Enumerate 2-4 technology options.\n"
                "3. **Compare** — Build a comparison matrix covering:\n"
                "   - Maturity and community support\n"
                "   - Performance characteristics\n"
                "   - Learning curve and team familiarity\n"
                "   - Licensing and cost\n"
                "   - Integration with existing stack\n"
                "4. **Recommend** — Pick the best option and justify the decision.\n"
                "5. **Document** — Save the evaluation to memory for future reference.\n\n"
                "## Output format\n"
                "Markdown comparison table + recommendation summary."
            ),
            "allowed_tools": ["search_memory", "create_task"],
            "metadata": {"category": "engineering", "complexity": "medium"},
        },
        {
            "name": "technical-debt-assessment",
            "description": "Assess and prioritize technical debt across the codebase.",
            "content": (
                "# Technical Debt Assessment\n\n"
                "## Objective\n"
                "Identify, categorize, and prioritize technical debt items.\n\n"
                "## Steps\n"
                "1. **Gather context** — Search memory for known debt items and past discussions.\n"
                "2. **Categorize** — Group debt by type:\n"
                "   - Code quality (duplication, complexity, missing tests)\n"
                "   - Architecture (coupling, missing abstractions)\n"
                "   - Infrastructure (outdated dependencies, manual processes)\n"
                "   - Documentation (missing or stale docs)\n"
                "3. **Prioritize** — Score each item by impact (1-5) and effort (1-5). "
                "Priority = impact / effort.\n"
                "4. **Create issues** — File a GitHub issue for each high-priority item.\n"
                "5. **Report** — Produce a summary with top-5 items to address next sprint.\n\n"
                "## Output format\n"
                "Prioritized list as markdown table with columns: Item, Category, Impact, Effort, Priority."
            ),
            "allowed_tools": ["search_memory", "github_create_issue", "create_task"],
            "metadata": {"category": "engineering", "complexity": "medium"},
        },
    ],
    # ── Backend Developer ────────────────────────────────────────────────
    "developer": [
        {
            "name": "api-design",
            "description": "Design RESTful API endpoints with request/response schemas.",
            "content": (
                "# API Design\n\n"
                "## Objective\n"
                "Design a clean, consistent REST API for the requested feature.\n\n"
                "## Steps\n"
                "1. **Identify resources** — Determine the domain entities involved.\n"
                "2. **Define endpoints** — For each resource:\n"
                "   - `POST /resource` — Create\n"
                "   - `GET /resource` — List (with pagination)\n"
                "   - `GET /resource/{id}` — Get by ID\n"
                "   - `PATCH /resource/{id}` — Partial update\n"
                "   - `DELETE /resource/{id}` — Delete\n"
                "3. **Define schemas** — Write Pydantic request/response models.\n"
                "4. **Define errors** — Map error cases to HTTP status codes (400, 404, 409, 422).\n"
                "5. **Write implementation** — Create FastAPI route file with typed endpoints.\n"
                "6. **Write tests** — Add pytest tests covering happy path and error cases.\n\n"
                "## Conventions\n"
                "- Use `snake_case` for fields\n"
                "- Use UUID for IDs\n"
                "- Return 201 for creation, 204 for deletion\n"
                "- Always require authentication via `require_scopes()`"
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "file_write",
                "git_clone",
                "git_commit_push",
                "github_create_pr",
            ],
            "metadata": {"category": "engineering", "complexity": "medium"},
        },
        {
            "name": "code-review",
            "description": "Review code changes for quality, security, and best practices.",
            "content": (
                "# Code Review\n\n"
                "## Objective\n"
                "Review a pull request or code diff for correctness, style, and security.\n\n"
                "## Checklist\n"
                "1. **Correctness** — Does the code do what it claims? Are edge cases handled?\n"
                "2. **Security** — Check for OWASP top-10 issues (injection, XSS, auth bypass).\n"
                "3. **Performance** — Look for N+1 queries, missing indexes, unbounded loops.\n"
                "4. **Style** — Follows project conventions (ruff, mypy, naming).\n"
                "5. **Tests** — Are there tests? Do they cover the key paths?\n"
                "6. **Documentation** — Are public APIs documented?\n\n"
                "## Output\n"
                "Post review comments on the PR. Approve, request changes, or comment."
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "github_comment",
                "github_create_pr",
            ],
            "metadata": {"category": "engineering", "complexity": "medium"},
        },
        {
            "name": "database-migration",
            "description": "Plan and implement a database schema change with Alembic migration.",
            "content": (
                "# Database Migration\n\n"
                "## Objective\n"
                "Implement a database schema change safely with an Alembic migration.\n\n"
                "## Steps\n"
                "1. **Design the change** — Define new tables, columns, or constraints needed.\n"
                "2. **Write the model** — Update or create the SQLAlchemy model in `app/models/`.\n"
                "3. **Create migration** — Write an Alembic migration file in `alembic/versions/`:\n"
                "   - Use sequential revision numbering (check existing revisions)\n"
                "   - Include both `upgrade()` and `downgrade()` functions\n"
                "   - Use `op.create_table`, `op.add_column`, `op.drop_column`, etc.\n"
                "4. **Test locally** — Run `alembic upgrade head` and `alembic downgrade -1`.\n"
                "5. **Update related code** — Schemas, routes, services as needed.\n"
                "6. **Commit and push** — Create a PR with the migration.\n\n"
                "## Conventions\n"
                "- Always use `server_default` for new NOT NULL columns\n"
                "- Use JSONB for flexible structured data\n"
                "- Add indexes for foreign keys and frequently queried columns"
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "file_write",
                "git_clone",
                "git_commit_push",
                "github_create_pr",
                "postgres_query",
            ],
            "metadata": {"category": "engineering", "complexity": "high"},
        },
        {
            "name": "bug-investigation",
            "description": "Investigate and diagnose a production bug from logs and code.",
            "content": (
                "# Bug Investigation\n\n"
                "## Objective\n"
                "Investigate a reported bug, find the root cause, and propose a fix.\n\n"
                "## Steps\n"
                "1. **Reproduce** — Understand the reproduction steps and expected vs actual behavior.\n"
                "2. **Check logs** — Query CI logs and execution logs for related errors.\n"
                "3. **Read the code** — Trace the execution path from the entry point.\n"
                "4. **Identify root cause** — Pinpoint the exact line or logic error.\n"
                "5. **Write the fix** — Implement the minimal change that fixes the bug.\n"
                "6. **Add a test** — Write a regression test that fails before the fix.\n"
                "7. **Create a PR** — Submit the fix with a clear description.\n\n"
                "## Output\n"
                "GitHub PR with the fix + comment on the original issue explaining root cause."
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "file_write",
                "github_list_runs",
                "github_get_run_logs",
                "github_create_pr",
                "github_comment",
                "postgres_query",
            ],
            "metadata": {"category": "engineering", "complexity": "high"},
        },
    ],
    # ── Frontend Developer ───────────────────────────────────────────────
    "frontend": [
        {
            "name": "component-development",
            "description": "Build a reusable React/TypeScript UI component.",
            "content": (
                "# Component Development\n\n"
                "## Objective\n"
                "Build a reusable, accessible React component following project conventions.\n\n"
                "## Steps\n"
                "1. **Define props** — Write a TypeScript interface for the component props.\n"
                "2. **Implement** — Build the component with proper state management.\n"
                "3. **Style** — Use the project's design system (tokens, spacing, colors).\n"
                "4. **Accessibility** — Add ARIA attributes, keyboard navigation, focus management.\n"
                "5. **Tests** — Write unit tests with React Testing Library.\n"
                "6. **Storybook** — Add a story showing the component in different states.\n"
                "7. **PR** — Submit with screenshots of the component.\n\n"
                "## Conventions\n"
                "- One component per file\n"
                "- Props interface named `{Component}Props`\n"
                "- Use `forwardRef` for interactive elements\n"
                "- Export from barrel index"
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "file_write",
                "git_clone",
                "git_commit_push",
                "github_create_pr",
            ],
            "metadata": {"category": "engineering", "complexity": "medium"},
        },
        {
            "name": "ui-review",
            "description": "Review a UI implementation for accessibility and UX quality.",
            "content": (
                "# UI Review\n\n"
                "## Objective\n"
                "Review a frontend implementation for UX quality and accessibility compliance.\n\n"
                "## Checklist\n"
                "1. **Visual consistency** — Matches design system (spacing, colors, typography).\n"
                "2. **Responsiveness** — Works on mobile, tablet, and desktop viewports.\n"
                "3. **Accessibility** — WCAG 2.1 AA: color contrast, keyboard nav, screen reader.\n"
                "4. **Performance** — No unnecessary re-renders, lazy loading for heavy content.\n"
                "5. **Error states** — Loading, empty, and error states are handled gracefully.\n"
                "6. **Interactions** — Hover, focus, and active states are defined.\n\n"
                "## Output\n"
                "Review comments on the PR with specific improvement suggestions."
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "github_comment",
            ],
            "metadata": {"category": "engineering", "complexity": "medium"},
        },
        {
            "name": "performance-audit",
            "description": "Audit frontend performance: bundle size, rendering, and network.",
            "content": (
                "# Frontend Performance Audit\n\n"
                "## Objective\n"
                "Identify and fix frontend performance bottlenecks.\n\n"
                "## Steps\n"
                "1. **Bundle analysis** — Check bundle size and identify heavy dependencies.\n"
                "2. **Render profiling** — Look for unnecessary re-renders and expensive computations.\n"
                "3. **Network** — Check for waterfall requests, missing caching headers.\n"
                "4. **Images** — Verify lazy loading, proper sizing, and modern formats (WebP).\n"
                "5. **Code splitting** — Ensure routes and heavy components are lazy loaded.\n"
                "6. **Recommendations** — Prioritize fixes by impact.\n\n"
                "## Output\n"
                "Create GitHub issues for each optimization with expected impact."
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "github_create_issue",
                "github_list_runs",
                "github_get_run_logs",
            ],
            "metadata": {"category": "engineering", "complexity": "high"},
        },
    ],
    # ── DevOps Engineer ──────────────────────────────────────────────────
    "devops": [
        {
            "name": "incident-response",
            "description": "Respond to a production incident: diagnose, mitigate, and document.",
            "content": (
                "# Incident Response\n\n"
                "## Objective\n"
                "Diagnose and resolve a production incident as quickly as possible.\n\n"
                "## Steps\n"
                "1. **Assess severity** — Determine impact: users affected, data at risk, revenue impact.\n"
                "2. **Communicate** — Notify the team via task creation with severity level.\n"
                "3. **Diagnose** — Check logs, metrics, and recent deployments.\n"
                "4. **Mitigate** — Apply immediate fix (rollback, scale, feature flag, hotfix).\n"
                "5. **Verify** — Confirm the incident is resolved via health checks.\n"
                "6. **Post-mortem** — Document timeline, root cause, and action items.\n\n"
                "## Severity levels\n"
                "- **SEV1**: Service down, all users affected → immediate response\n"
                "- **SEV2**: Degraded service, partial impact → respond within 30 min\n"
                "- **SEV3**: Minor issue, workaround available → respond within 2 hours"
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "http_request",
                "github_create_issue",
                "github_list_runs",
                "github_get_run_logs",
                "service_call",
                "postgres_query",
            ],
            "metadata": {"category": "operations", "complexity": "high"},
        },
        {
            "name": "deployment-pipeline",
            "description": "Set up or update a CI/CD pipeline for a service.",
            "content": (
                "# Deployment Pipeline\n\n"
                "## Objective\n"
                "Configure or improve a CI/CD pipeline for automated testing and deployment.\n\n"
                "## Steps\n"
                "1. **Review current pipeline** — Read existing GitHub Actions workflows.\n"
                "2. **Define stages** — Lint → Test → Build → Deploy (staging → production).\n"
                "3. **Write workflow** — Create/update `.github/workflows/` files.\n"
                "4. **Add checks** — Ruff, mypy, pytest with coverage threshold.\n"
                "5. **Configure deployment** — Docker build, push to registry, deploy to target.\n"
                "6. **Add notifications** — Slack/email on failure.\n"
                "7. **Test** — Push a branch and verify the pipeline runs correctly.\n\n"
                "## Conventions\n"
                "- Use reusable workflows where possible\n"
                "- Pin action versions with SHA\n"
                "- Never store secrets in workflow files — use GitHub Secrets"
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "file_write",
                "git_clone",
                "git_commit_push",
                "github_create_pr",
                "github_list_runs",
                "github_get_run_logs",
            ],
            "metadata": {"category": "operations", "complexity": "medium"},
        },
        {
            "name": "infrastructure-review",
            "description": "Review and optimize infrastructure configuration and costs.",
            "content": (
                "# Infrastructure Review\n\n"
                "## Objective\n"
                "Review infrastructure setup for reliability, security, and cost efficiency.\n\n"
                "## Checklist\n"
                "1. **High availability** — No single points of failure, auto-scaling configured.\n"
                "2. **Security** — Network segmentation, secrets management, TLS everywhere.\n"
                "3. **Monitoring** — Health checks, alerting thresholds, dashboards.\n"
                "4. **Backups** — Database backups scheduled and tested.\n"
                "5. **Cost** — Right-sized instances, reserved capacity, unused resources.\n"
                "6. **Documentation** — Runbooks and architecture diagrams up to date.\n\n"
                "## Output\n"
                "Prioritized list of improvements as GitHub issues."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "http_request",
                "github_create_issue",
                "service_call",
                "analytics_overview",
                "auth_list_clients",
            ],
            "metadata": {"category": "operations", "complexity": "high"},
        },
    ],
    # ── Product Manager ──────────────────────────────────────────────────
    "product_manager": [
        {
            "name": "user-story-writing",
            "description": "Write detailed user stories with acceptance criteria.",
            "content": (
                "# User Story Writing\n\n"
                "## Objective\n"
                "Write clear, actionable user stories ready for sprint planning.\n\n"
                "## Template\n"
                "**As a** [user type], **I want** [action], **so that** [benefit].\n\n"
                "## Steps\n"
                "1. **Identify the user** — Who benefits from this feature?\n"
                "2. **Define the need** — What problem does it solve?\n"
                "3. **Write acceptance criteria** — Use Given/When/Then format:\n"
                "   - Given [context], When [action], Then [expected result]\n"
                "4. **Add technical notes** — API changes, data model impacts, dependencies.\n"
                "5. **Estimate size** — T-shirt size (S/M/L/XL) based on complexity.\n"
                "6. **Create issue** — File as a GitHub issue with proper labels.\n\n"
                "## Quality checks\n"
                "- INVEST: Independent, Negotiable, Valuable, Estimable, Small, Testable\n"
                "- Each story should be completable in one sprint"
            ),
            "allowed_tools": [
                "search_memory",
                "github_create_issue",
                "github_comment",
                "team_status",
            ],
            "metadata": {"category": "product", "complexity": "low"},
        },
        {
            "name": "feature-spec",
            "description": "Write a detailed feature specification document.",
            "content": (
                "# Feature Specification\n\n"
                "## Objective\n"
                "Produce a comprehensive feature spec that engineering can implement.\n\n"
                "## Sections\n"
                "1. **Problem statement** — What problem are we solving and for whom?\n"
                "2. **Goals and non-goals** — What is in scope and explicitly out of scope?\n"
                "3. **User flows** — Step-by-step user journey with decision points.\n"
                "4. **Requirements** — Functional (must-have, nice-to-have) and non-functional.\n"
                "5. **API surface** — Endpoints, request/response shapes.\n"
                "6. **Data model** — New or changed entities.\n"
                "7. **Analytics** — Events to track, success metrics.\n"
                "8. **Rollout plan** — Feature flag, staged rollout, or big bang.\n"
                "9. **Open questions** — Unresolved decisions.\n\n"
                "## Output\n"
                "Create a GitHub issue with the full spec and break down into implementation tasks."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "github_create_issue",
                "github_comment",
                "analytics_overview",
                "analytics_pages",
            ],
            "metadata": {"category": "product", "complexity": "high"},
        },
        {
            "name": "sprint-planning",
            "description": "Prepare and facilitate sprint planning with prioritized backlog.",
            "content": (
                "# Sprint Planning\n\n"
                "## Objective\n"
                "Prepare the next sprint with a prioritized, estimated backlog.\n\n"
                "## Steps\n"
                "1. **Review team status** — Check current sprint progress and velocity.\n"
                "2. **Groom backlog** — Ensure top items have acceptance criteria and estimates.\n"
                "3. **Prioritize** — Rank by business value vs effort (use RICE or MoSCoW).\n"
                "4. **Set sprint goal** — One clear, measurable objective.\n"
                "5. **Allocate capacity** — Account for team availability and carry-over.\n"
                "6. **Communicate** — Create a sprint summary with the selected items.\n\n"
                "## Metrics\n"
                "- Velocity: average story points completed per sprint\n"
                "- Carry-over rate: items not completed from previous sprint\n"
                "- Sprint goal success rate"
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "team_status",
                "github_create_issue",
                "github_comment",
            ],
            "metadata": {"category": "product", "complexity": "medium"},
        },
    ],
    # ── UX Designer ──────────────────────────────────────────────────────
    "designer": [
        {
            "name": "design-review",
            "description": "Review a UI implementation against design specifications.",
            "content": (
                "# Design Review\n\n"
                "## Objective\n"
                "Verify that a UI implementation matches the intended design.\n\n"
                "## Checklist\n"
                "1. **Layout** — Spacing, alignment, and grid system.\n"
                "2. **Typography** — Font family, sizes, weights, line height.\n"
                "3. **Colors** — Correct palette tokens, contrast ratios.\n"
                "4. **Components** — Design system components used correctly.\n"
                "5. **States** — Hover, active, disabled, loading, error, empty states.\n"
                "6. **Responsiveness** — Adapts to mobile, tablet, desktop.\n"
                "7. **Micro-interactions** — Transitions, animations, feedback.\n\n"
                "## Output\n"
                "Comment on the GitHub issue with specific visual feedback."
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "github_comment",
            ],
            "metadata": {"category": "design", "complexity": "medium"},
        },
        {
            "name": "wireframe-creation",
            "description": "Create text-based wireframes and user flow descriptions.",
            "content": (
                "# Wireframe Creation\n\n"
                "## Objective\n"
                "Define the layout and user flow for a new feature using text-based wireframes.\n\n"
                "## Steps\n"
                "1. **Understand the feature** — Read the spec or user story.\n"
                "2. **Map the flow** — List screens and transitions between them.\n"
                "3. **Sketch layout** — Use ASCII art or structured markdown:\n"
                "   ```\n"
                "   ┌─────────────────────┐\n"
                "   │ Header              │\n"
                "   ├─────────────────────┤\n"
                "   │ [Search input     ] │\n"
                "   │ ┌─────┐ ┌─────┐    │\n"
                "   │ │Card │ │Card │    │\n"
                "   │ └─────┘ └─────┘    │\n"
                "   └─────────────────────┘\n"
                "   ```\n"
                "4. **Define interactions** — What happens on click, hover, submit.\n"
                "5. **Document** — Save wireframes to a file and create a GitHub issue.\n\n"
                "## Conventions\n"
                "- Start with mobile layout, then scale up\n"
                "- Annotate interactive elements with behavior descriptions"
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "file_write",
                "github_create_issue",
            ],
            "metadata": {"category": "design", "complexity": "medium"},
        },
        {
            "name": "accessibility-audit",
            "description": "Audit a UI for WCAG 2.1 AA accessibility compliance.",
            "content": (
                "# Accessibility Audit\n\n"
                "## Objective\n"
                "Audit a UI for WCAG 2.1 Level AA compliance.\n\n"
                "## Checklist\n"
                "1. **Perceivable**\n"
                "   - All images have alt text\n"
                "   - Color is not the only means of conveying information\n"
                "   - Text contrast ratio >= 4.5:1 (3:1 for large text)\n"
                "2. **Operable**\n"
                "   - All interactive elements are keyboard accessible\n"
                "   - Focus order is logical\n"
                "   - No keyboard traps\n"
                "3. **Understandable**\n"
                "   - Form inputs have visible labels\n"
                "   - Error messages are descriptive\n"
                "   - Language attribute set on `<html>`\n"
                "4. **Robust**\n"
                "   - Valid HTML semantics\n"
                "   - ARIA roles used correctly\n"
                "   - Works with screen readers\n\n"
                "## Output\n"
                "List of issues with severity (Critical, Major, Minor) and fix suggestions."
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "github_create_issue",
            ],
            "metadata": {"category": "design", "complexity": "high"},
        },
    ],
    # ── QA Engineer ──────────────────────────────────────────────────────
    "qa": [
        {
            "name": "test-plan",
            "description": "Write a comprehensive test plan for a feature or release.",
            "content": (
                "# Test Plan\n\n"
                "## Objective\n"
                "Create a structured test plan covering all aspects of a feature.\n\n"
                "## Sections\n"
                "1. **Scope** — What is being tested and what is out of scope.\n"
                "2. **Test scenarios** — For each user flow:\n"
                "   - Happy path\n"
                "   - Edge cases\n"
                "   - Error cases\n"
                "   - Boundary values\n"
                "3. **Test types** — Unit, integration, e2e, performance, security.\n"
                "4. **Environment** — Required setup, test data, dependencies.\n"
                "5. **Automation** — Which tests to automate, which are manual.\n"
                "6. **Exit criteria** — Conditions for passing (coverage %, zero critical bugs).\n\n"
                "## Output\n"
                "GitHub issue with the test plan. Create sub-issues for each test scenario."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "github_create_issue",
                "github_comment",
                "file_read",
            ],
            "metadata": {"category": "quality", "complexity": "medium"},
        },
        {
            "name": "bug-report",
            "description": "Create a detailed bug report with reproduction steps.",
            "content": (
                "# Bug Report\n\n"
                "## Objective\n"
                "File a clear, reproducible bug report.\n\n"
                "## Template\n"
                "### Summary\n"
                "One-line description of the issue.\n\n"
                "### Steps to reproduce\n"
                "1. Step 1\n"
                "2. Step 2\n"
                "3. Step 3\n\n"
                "### Expected behavior\n"
                "What should happen.\n\n"
                "### Actual behavior\n"
                "What actually happens.\n\n"
                "### Environment\n"
                "- OS / Browser / Version\n"
                "- API version\n"
                "- Relevant config\n\n"
                "### Severity\n"
                "- **Critical**: Data loss, security breach, service down\n"
                "- **Major**: Feature broken, no workaround\n"
                "- **Minor**: Feature broken, workaround exists\n"
                "- **Cosmetic**: Visual issue, no functional impact\n\n"
                "### Additional context\n"
                "Logs, screenshots, related issues.\n\n"
                "## Output\n"
                "GitHub issue with the bug report and appropriate labels."
            ),
            "allowed_tools": [
                "search_memory",
                "github_create_issue",
                "github_list_runs",
                "github_get_run_logs",
            ],
            "metadata": {"category": "quality", "complexity": "low"},
        },
        {
            "name": "release-validation",
            "description": "Validate a release candidate before deployment to production.",
            "content": (
                "# Release Validation\n\n"
                "## Objective\n"
                "Validate that a release candidate is ready for production deployment.\n\n"
                "## Steps\n"
                "1. **Check CI** — All pipeline checks pass (lint, tests, build).\n"
                "2. **Review coverage** — Coverage meets threshold (target: 100%).\n"
                "3. **Smoke tests** — Run critical path tests on staging.\n"
                "4. **Regression** — No existing features broken.\n"
                "5. **Performance** — Response times within acceptable range.\n"
                "6. **Database** — Migrations run cleanly (up and down).\n"
                "7. **Sign off** — Comment on the release issue with validation result.\n\n"
                "## Verdict\n"
                "- **GO**: All checks pass, ready to deploy\n"
                "- **NO-GO**: List blockers that must be fixed first"
            ),
            "allowed_tools": [
                "search_memory",
                "github_comment",
                "github_list_runs",
                "github_get_run_logs",
                "postgres_query",
            ],
            "metadata": {"category": "quality", "complexity": "high"},
        },
    ],
    # ── Data Analyst ─────────────────────────────────────────────────────
    "data_analyst": [
        {
            "name": "metrics-report",
            "description": "Generate a product metrics report with key KPIs.",
            "content": (
                "# Metrics Report\n\n"
                "## Objective\n"
                "Produce a periodic report on key product and business metrics.\n\n"
                "## Steps\n"
                "1. **Gather data** — Query analytics and billing APIs for the period.\n"
                "2. **Compute KPIs** — Calculate:\n"
                "   - Active users (DAU, WAU, MAU)\n"
                "   - Retention rate\n"
                "   - Revenue (MRR, ARR)\n"
                "   - Conversion funnel\n"
                "   - Feature adoption\n"
                "3. **Compare** — Week-over-week and month-over-month trends.\n"
                "4. **Highlight anomalies** — Flag significant changes (>10% deviation).\n"
                "5. **Recommend** — Suggest actions based on the data.\n\n"
                "## Output\n"
                "Markdown report with tables and inline metrics. Save to memory for tracking."
            ),
            "allowed_tools": [
                "search_memory",
                "postgres_query",
                "analytics_overview",
                "analytics_pages",
                "billing_list_subscriptions",
            ],
            "metadata": {"category": "analytics", "complexity": "medium"},
        },
        {
            "name": "cohort-analysis",
            "description": "Perform user cohort analysis to understand retention patterns.",
            "content": (
                "# Cohort Analysis\n\n"
                "## Objective\n"
                "Analyze user retention by signup cohort.\n\n"
                "## Steps\n"
                "1. **Define cohorts** — Group users by signup week or month.\n"
                "2. **Track activity** — For each cohort, measure activity at day 1, 7, 14, 30.\n"
                "3. **Build matrix** — Create a retention matrix (cohort x time period).\n"
                "4. **Identify patterns** — Which cohorts retain better? What changed?\n"
                "5. **Correlate** — Cross-reference with product changes and campaigns.\n"
                "6. **Recommend** — Suggest improvements to onboarding and engagement.\n\n"
                "## Output\n"
                "Retention matrix as markdown table + insights summary."
            ),
            "allowed_tools": [
                "search_memory",
                "postgres_query",
                "analytics_overview",
                "analytics_pages",
            ],
            "metadata": {"category": "analytics", "complexity": "high"},
        },
        {
            "name": "ab-test-analysis",
            "description": "Analyze A/B test results for statistical significance.",
            "content": (
                "# A/B Test Analysis\n\n"
                "## Objective\n"
                "Analyze an A/B test and determine if results are statistically significant.\n\n"
                "## Steps\n"
                "1. **Gather data** — Collect metrics for control and variant groups.\n"
                "2. **Check sample size** — Verify sufficient data for statistical power.\n"
                "3. **Compute metrics** — Conversion rate, average value, standard deviation.\n"
                "4. **Test significance** — Calculate p-value (target < 0.05).\n"
                "5. **Check practical significance** — Is the effect size meaningful?\n"
                "6. **Recommend** — Ship variant, extend test, or discard.\n\n"
                "## Output\n"
                "Analysis report with statistical details and clear recommendation."
            ),
            "allowed_tools": [
                "search_memory",
                "postgres_query",
                "analytics_overview",
                "analytics_campaigns",
            ],
            "metadata": {"category": "analytics", "complexity": "high"},
        },
    ],
    # ── Marketing Specialist ─────────────────────────────────────────────
    "marketing": [
        {
            "name": "blog-post",
            "description": "Write and prepare a blog post for publication.",
            "content": (
                "# Blog Post\n\n"
                "## Objective\n"
                "Write a high-quality blog post aligned with the content strategy.\n\n"
                "## Steps\n"
                "1. **Research** — Identify target keywords and audience intent.\n"
                "2. **Outline** — Structure with: Hook, Problem, Solution, CTA.\n"
                "3. **Write** — Draft the post (800-1500 words).\n"
                "4. **SEO** — Optimize title, meta description, headers, internal links.\n"
                "5. **Review** — Check grammar, tone, and brand voice consistency.\n"
                "6. **Distribute** — Plan social media posts and newsletter inclusion.\n\n"
                "## Conventions\n"
                "- Use short paragraphs (2-3 sentences)\n"
                "- Include at least one code example for technical posts\n"
                "- End with a clear call-to-action"
            ),
            "allowed_tools": [
                "search_memory",
                "http_request",
                "mailler_send_email",
                "mailler_list_templates",
            ],
            "metadata": {"category": "marketing", "complexity": "medium"},
        },
        {
            "name": "campaign-launch",
            "description": "Plan and launch a marketing campaign across channels.",
            "content": (
                "# Campaign Launch\n\n"
                "## Objective\n"
                "Plan and execute a multi-channel marketing campaign.\n\n"
                "## Steps\n"
                "1. **Define goal** — What metric are we trying to move? (signups, activation, revenue)\n"
                "2. **Target audience** — Define the segment and persona.\n"
                "3. **Create content** — Write copy for each channel:\n"
                "   - Email (subject line, body, CTA)\n"
                "   - Social media (post copy, hashtags)\n"
                "   - Landing page (headline, value prop)\n"
                "4. **Schedule** — Set launch date and cadence.\n"
                "5. **Launch** — Start the campaign via email and social tools.\n"
                "6. **Monitor** — Track open rates, click rates, conversions.\n"
                "7. **Report** — Summarize results after the campaign ends.\n\n"
                "## Metrics\n"
                "- Email open rate target: >25%\n"
                "- Click-through rate target: >3%\n"
                "- Conversion rate target: >1%"
            ),
            "allowed_tools": [
                "search_memory",
                "http_request",
                "mailler_send_email",
                "mailler_start_campaign",
                "mailler_get_stats",
                "analytics_campaigns",
            ],
            "metadata": {"category": "marketing", "complexity": "high"},
        },
        {
            "name": "seo-audit",
            "description": "Audit website SEO and recommend improvements.",
            "content": (
                "# SEO Audit\n\n"
                "## Objective\n"
                "Audit the website for SEO issues and recommend optimizations.\n\n"
                "## Checklist\n"
                "1. **Technical SEO**\n"
                "   - Page load speed\n"
                "   - Mobile-friendliness\n"
                "   - Sitemap and robots.txt\n"
                "   - HTTPS everywhere\n"
                "2. **On-page SEO**\n"
                "   - Title tags and meta descriptions\n"
                "   - Header hierarchy (H1 > H2 > H3)\n"
                "   - Internal linking structure\n"
                "   - Image alt attributes\n"
                "3. **Content**\n"
                "   - Keyword coverage and density\n"
                "   - Content freshness and depth\n"
                "   - Duplicate content issues\n"
                "4. **Off-page**\n"
                "   - Backlink profile\n"
                "   - Domain authority\n\n"
                "## Output\n"
                "Prioritized list of SEO improvements with expected impact."
            ),
            "allowed_tools": [
                "search_memory",
                "http_request",
                "analytics_overview",
                "analytics_pages",
            ],
            "metadata": {"category": "marketing", "complexity": "medium"},
        },
    ],
    # ── Security Engineer ────────────────────────────────────────────────
    "security": [
        {
            "name": "security-audit",
            "description": "Perform a security audit on code and infrastructure.",
            "content": (
                "# Security Audit\n\n"
                "## Objective\n"
                "Audit the application for security vulnerabilities.\n\n"
                "## Scope\n"
                "1. **Authentication** — Token validation, session management, MFA.\n"
                "2. **Authorization** — Role-based access, scope enforcement, privilege escalation.\n"
                "3. **Input validation** — SQL injection, XSS, command injection, path traversal.\n"
                "4. **Data protection** — Encryption at rest and in transit, PII handling.\n"
                "5. **Dependencies** — Known CVEs in third-party packages.\n"
                "6. **Infrastructure** — Network exposure, secrets management, logging.\n"
                "7. **API security** — Rate limiting, CORS, error disclosure.\n\n"
                "## Output\n"
                "Security report with findings categorized by severity (Critical, High, Medium, Low). "
                "Create GitHub issues for each finding."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "file_read",
                "github_create_issue",
                "github_comment",
                "service_call",
                "auth_list_users",
                "auth_list_clients",
            ],
            "metadata": {"category": "security", "complexity": "high"},
        },
        {
            "name": "vulnerability-assessment",
            "description": "Assess and prioritize a reported vulnerability.",
            "content": (
                "# Vulnerability Assessment\n\n"
                "## Objective\n"
                "Evaluate a reported vulnerability and determine the appropriate response.\n\n"
                "## Steps\n"
                "1. **Verify** — Confirm the vulnerability is real and reproducible.\n"
                "2. **Assess impact** — What data or functionality is at risk?\n"
                "3. **Score** — Use CVSS v3 scoring:\n"
                "   - Attack vector (Network, Adjacent, Local, Physical)\n"
                "   - Attack complexity (Low, High)\n"
                "   - Privileges required (None, Low, High)\n"
                "   - User interaction (None, Required)\n"
                "   - Impact (Confidentiality, Integrity, Availability)\n"
                "4. **Prioritize** — Critical (9.0+), High (7.0-8.9), Medium (4.0-6.9), Low (<4.0).\n"
                "5. **Remediate** — Define and assign the fix.\n"
                "6. **Verify fix** — Confirm the vulnerability is resolved.\n\n"
                "## Output\n"
                "Assessment report with CVSS score and remediation plan."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "file_read",
                "github_create_issue",
                "http_request",
            ],
            "metadata": {"category": "security", "complexity": "high"},
        },
        {
            "name": "access-review",
            "description": "Review user access, roles, and permissions for compliance.",
            "content": (
                "# Access Review\n\n"
                "## Objective\n"
                "Review all user and service account access for least-privilege compliance.\n\n"
                "## Steps\n"
                "1. **List users** — Get all users and their roles from the auth system.\n"
                "2. **List clients** — Get all machine clients and their scopes.\n"
                "3. **Review roles** — For each role, verify the assigned permissions are necessary.\n"
                "4. **Check stale accounts** — Identify inactive users (>90 days).\n"
                "5. **Check over-privileged** — Flag users with admin/wildcard scopes.\n"
                "6. **Recommend** — Suggest permission changes and account deactivations.\n\n"
                "## Output\n"
                "Access review report with action items."
            ),
            "allowed_tools": [
                "search_memory",
                "auth_list_users",
                "auth_list_clients",
                "auth_list_roles",
            ],
            "metadata": {"category": "security", "complexity": "medium"},
        },
    ],
    # ── Sales Representative ─────────────────────────────────────────────
    "sales": [
        {
            "name": "proposal-writing",
            "description": "Write a tailored sales proposal for a prospect.",
            "content": (
                "# Sales Proposal\n\n"
                "## Objective\n"
                "Create a personalized proposal that demonstrates value for the prospect.\n\n"
                "## Structure\n"
                "1. **Executive summary** — Their problem, our solution, expected outcome.\n"
                "2. **Understanding** — Restate the prospect's needs and challenges.\n"
                "3. **Solution** — How our product solves their specific problems.\n"
                "4. **Features** — Key features mapped to their use cases.\n"
                "5. **Pricing** — Transparent pricing with options (tiers, annual vs monthly).\n"
                "6. **Timeline** — Onboarding and implementation schedule.\n"
                "7. **Social proof** — Relevant case studies and testimonials.\n"
                "8. **Next steps** — Clear CTA (schedule demo, start trial, sign contract).\n\n"
                "## Output\n"
                "Send the proposal via email and log the activity in memory."
            ),
            "allowed_tools": [
                "search_memory",
                "http_request",
                "mailler_send_email",
                "billing_get_customer",
            ],
            "metadata": {"category": "sales", "complexity": "medium"},
        },
        {
            "name": "lead-qualification",
            "description": "Qualify and score an inbound lead using BANT criteria.",
            "content": (
                "# Lead Qualification\n\n"
                "## Objective\n"
                "Evaluate and score an inbound lead to determine sales-readiness.\n\n"
                "## Framework: BANT\n"
                "1. **Budget** — Can they afford the solution? Score 1-5.\n"
                "2. **Authority** — Is the contact a decision-maker? Score 1-5.\n"
                "3. **Need** — Do they have a clear problem we solve? Score 1-5.\n"
                "4. **Timeline** — When do they need a solution? Score 1-5.\n\n"
                "## Scoring\n"
                "- **Hot** (16-20): Ready for demo, fast-track\n"
                "- **Warm** (10-15): Nurture with content, schedule follow-up\n"
                "- **Cold** (<10): Add to nurture sequence, revisit in 90 days\n\n"
                "## Output\n"
                "Lead score with rationale. Create follow-up task based on score."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "http_request",
                "service_call",
            ],
            "metadata": {"category": "sales", "complexity": "low"},
        },
        {
            "name": "demo-preparation",
            "description": "Prepare a personalized product demo for a prospect.",
            "content": (
                "# Demo Preparation\n\n"
                "## Objective\n"
                "Prepare a tailored product demo that addresses the prospect's specific needs.\n\n"
                "## Steps\n"
                "1. **Research** — Review the prospect's company, industry, and pain points.\n"
                "2. **Customize** — Select features and workflows most relevant to them.\n"
                "3. **Script** — Write a demo script with:\n"
                "   - Opening (2 min): Company intro, agenda\n"
                "   - Discovery (5 min): Confirm their needs\n"
                "   - Demo (15 min): Show relevant features\n"
                "   - Q&A (5 min): Address questions\n"
                "   - Close (3 min): Next steps, pricing overview\n"
                "4. **Prepare data** — Set up demo environment with realistic data.\n"
                "5. **Practice** — Run through the demo once.\n\n"
                "## Output\n"
                "Demo script and preparation notes saved to memory."
            ),
            "allowed_tools": [
                "search_memory",
                "http_request",
                "billing_list_subscriptions",
                "billing_get_customer",
            ],
            "metadata": {"category": "sales", "complexity": "medium"},
        },
    ],
    # ── CEO ──────────────────────────────────────────────────────────────
    "ceo": [
        {
            "name": "investor-update",
            "description": "Write a monthly investor update with key metrics and highlights.",
            "content": (
                "# Investor Update\n\n"
                "## Objective\n"
                "Write a concise monthly update for investors.\n\n"
                "## Structure\n"
                "1. **TL;DR** — 2-3 sentence summary of the month.\n"
                "2. **Key metrics** — MRR, growth rate, burn rate, runway, active users.\n"
                "3. **Wins** — Top 3 achievements this month.\n"
                "4. **Challenges** — Honest assessment of blockers or setbacks.\n"
                "5. **Product** — Major features shipped or in progress.\n"
                "6. **Team** — Hiring updates, team changes.\n"
                "7. **Asks** — Specific help needed from investors (intros, advice).\n"
                "8. **Next month** — Top 3 priorities.\n\n"
                "## Output\n"
                "Formatted update ready to send. Save to memory for tracking."
            ),
            "allowed_tools": [
                "search_memory",
                "team_status",
                "analytics_overview",
                "billing_list_subscriptions",
            ],
            "metadata": {"category": "leadership", "complexity": "medium"},
        },
        {
            "name": "strategic-review",
            "description": "Conduct a quarterly strategic review of company direction.",
            "content": (
                "# Strategic Review\n\n"
                "## Objective\n"
                "Review company strategy quarterly and adjust direction.\n\n"
                "## Framework\n"
                "1. **Mission check** — Are we still aligned with our mission?\n"
                "2. **Market** — How has the market evolved? New competitors or opportunities?\n"
                "3. **Product-market fit** — Are users engaged? NPS trending up or down?\n"
                "4. **Financial health** — Revenue, burn, runway. On track for milestones?\n"
                "5. **Team health** — Velocity, morale, hiring needs.\n"
                "6. **OKR review** — Score last quarter's OKRs. Set next quarter's.\n"
                "7. **Risks** — Top 3 threats and mitigation plans.\n"
                "8. **Decisions** — List strategic decisions to make with options and tradeoffs.\n\n"
                "## Output\n"
                "Strategic review document with decisions and action items."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "team_status",
                "analytics_overview",
                "billing_list_subscriptions",
                "billing_get_customer",
                "auth_list_users",
            ],
            "metadata": {"category": "leadership", "complexity": "high"},
        },
        {
            "name": "pitch-deck",
            "description": "Create or update the company pitch deck content.",
            "content": (
                "# Pitch Deck\n\n"
                "## Objective\n"
                "Create compelling pitch deck content for fundraising or partnerships.\n\n"
                "## Slides\n"
                "1. **Cover** — Company name, tagline, logo.\n"
                "2. **Problem** — The pain point, who has it, how big.\n"
                "3. **Solution** — What we do, how it works.\n"
                "4. **Product** — Key screens or demo.\n"
                "5. **Market** — TAM, SAM, SOM.\n"
                "6. **Business model** — How we make money.\n"
                "7. **Traction** — Key metrics, growth chart.\n"
                "8. **Team** — Founders and key hires.\n"
                "9. **Competition** — Positioning matrix.\n"
                "10. **Financials** — Revenue, projections, unit economics.\n"
                "11. **Ask** — Funding amount, use of funds, milestones.\n\n"
                "## Output\n"
                "Slide content as structured markdown. Each slide should be one section."
            ),
            "allowed_tools": [
                "search_memory",
                "team_status",
                "analytics_overview",
                "billing_list_subscriptions",
            ],
            "metadata": {"category": "leadership", "complexity": "high"},
        },
    ],
    # ── CFO ──────────────────────────────────────────────────────────────
    "cfo": [
        {
            "name": "financial-report",
            "description": "Generate a periodic financial report with P&L and cash flow.",
            "content": (
                "# Financial Report\n\n"
                "## Objective\n"
                "Produce a financial report covering revenue, expenses, and cash position.\n\n"
                "## Sections\n"
                "1. **Revenue** — MRR, ARR, revenue by plan, growth rate.\n"
                "2. **Expenses** — By category (infra, payroll, tools, marketing).\n"
                "3. **P&L** — Revenue minus expenses, gross margin.\n"
                "4. **Cash flow** — Cash in, cash out, net burn rate.\n"
                "5. **Runway** — Months of runway at current burn.\n"
                "6. **Unit economics** — CAC, LTV, LTV/CAC ratio.\n"
                "7. **Forecast** — 3-month projection based on current trends.\n\n"
                "## Output\n"
                "Financial report as markdown tables. Save to memory."
            ),
            "allowed_tools": [
                "search_memory",
                "postgres_query",
                "billing_list_subscriptions",
                "billing_get_subscription",
                "billing_get_customer",
                "billing_report_usage",
            ],
            "metadata": {"category": "finance", "complexity": "high"},
        },
        {
            "name": "budget-review",
            "description": "Review and adjust departmental budgets.",
            "content": (
                "# Budget Review\n\n"
                "## Objective\n"
                "Review budget allocation and actual spend, recommend adjustments.\n\n"
                "## Steps\n"
                "1. **Gather actuals** — Pull actual spend by department from billing and services.\n"
                "2. **Compare to budget** — Calculate variance (actual vs planned).\n"
                "3. **Identify overruns** — Flag categories >10% over budget.\n"
                "4. **Identify savings** — Flag categories >20% under budget (reallocate?).\n"
                "5. **Forecast** — Project end-of-quarter spend based on current trajectory.\n"
                "6. **Recommend** — Suggest budget adjustments with rationale.\n\n"
                "## Output\n"
                "Budget vs actual table with variance analysis and recommendations."
            ),
            "allowed_tools": [
                "search_memory",
                "postgres_query",
                "service_call",
                "billing_list_subscriptions",
                "billing_report_usage",
            ],
            "metadata": {"category": "finance", "complexity": "medium"},
        },
        {
            "name": "pricing-analysis",
            "description": "Analyze and optimize product pricing strategy.",
            "content": (
                "# Pricing Analysis\n\n"
                "## Objective\n"
                "Evaluate current pricing and recommend optimizations.\n\n"
                "## Steps\n"
                "1. **Current state** — List all plans, prices, and feature tiers.\n"
                "2. **Usage patterns** — Analyze which plans customers choose and why.\n"
                "3. **Revenue distribution** — Revenue by plan, concentration risk.\n"
                "4. **Competitor benchmarking** — How do we compare on price/value?\n"
                "5. **Elasticity** — Estimate impact of price changes on conversion.\n"
                "6. **Recommendations** — Propose changes with projected revenue impact.\n\n"
                "## Output\n"
                "Pricing analysis report with specific recommendations."
            ),
            "allowed_tools": [
                "search_memory",
                "http_request",
                "postgres_query",
                "billing_list_subscriptions",
                "billing_get_customer",
            ],
            "metadata": {"category": "finance", "complexity": "high"},
        },
    ],
    # ── Customer Support ─────────────────────────────────────────────────
    "support": [
        {
            "name": "ticket-triage",
            "description": "Triage incoming support tickets by priority and category.",
            "content": (
                "# Ticket Triage\n\n"
                "## Objective\n"
                "Classify and prioritize an incoming support ticket.\n\n"
                "## Steps\n"
                "1. **Read the ticket** — Understand the user's issue.\n"
                "2. **Categorize** — Bug, feature request, billing, account, how-to.\n"
                "3. **Prioritize** — Based on impact and urgency:\n"
                "   - **P1**: Service down, data loss, security issue → immediate\n"
                "   - **P2**: Feature broken, no workaround → respond within 4h\n"
                "   - **P3**: Feature broken, workaround exists → respond within 24h\n"
                "   - **P4**: Question, feature request → respond within 48h\n"
                "4. **Route** — Assign to the right team (engineering, billing, product).\n"
                "5. **Respond** — Send initial acknowledgment to the user.\n\n"
                "## Output\n"
                "Ticket classified, prioritized, and initial response sent."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "github_create_issue",
                "mailler_send_email",
            ],
            "metadata": {"category": "support", "complexity": "low"},
        },
        {
            "name": "faq-writing",
            "description": "Write FAQ articles for common user questions.",
            "content": (
                "# FAQ Writing\n\n"
                "## Objective\n"
                "Write clear, helpful FAQ articles for recurring user questions.\n\n"
                "## Template\n"
                "### Question\n"
                "State the question exactly as users ask it.\n\n"
                "### Answer\n"
                "1. **Short answer** — One-sentence direct answer.\n"
                "2. **Detailed explanation** — Step-by-step if applicable.\n"
                "3. **Examples** — Code samples, screenshots, or links.\n"
                "4. **Related** — Links to related FAQ articles.\n\n"
                "## Quality checks\n"
                "- Uses simple, non-technical language where possible\n"
                "- Includes concrete examples\n"
                "- Answers the question in the first sentence\n"
                "- Updated with current product behavior"
            ),
            "allowed_tools": [
                "search_memory",
                "http_request",
                "github_create_issue",
                "github_comment",
            ],
            "metadata": {"category": "support", "complexity": "low"},
        },
        {
            "name": "escalation-handling",
            "description": "Handle an escalated customer issue with care and resolution.",
            "content": (
                "# Escalation Handling\n\n"
                "## Objective\n"
                "Resolve an escalated customer issue with empathy and speed.\n\n"
                "## Steps\n"
                "1. **Review history** — Read all previous interactions and attempts.\n"
                "2. **Understand impact** — How is this affecting the customer's business?\n"
                "3. **Investigate** — Check billing, account status, and technical logs.\n"
                "4. **Resolve** — Fix the issue or provide a workaround.\n"
                "5. **Communicate** — Send a personalized response:\n"
                "   - Acknowledge the frustration\n"
                "   - Explain what happened\n"
                "   - Describe the fix\n"
                "   - Offer compensation if appropriate\n"
                "6. **Follow up** — Create a task to check back in 48 hours.\n"
                "7. **Prevent** — File a bug or feature request to prevent recurrence.\n\n"
                "## Output\n"
                "Resolution email sent, follow-up scheduled, root cause documented."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "billing_get_customer",
                "billing_get_subscription",
                "mailler_send_email",
                "github_create_issue",
            ],
            "metadata": {"category": "support", "complexity": "high"},
        },
    ],
    # ── Technical Writer ─────────────────────────────────────────────────
    "tech_writer": [
        {
            "name": "api-documentation",
            "description": "Write comprehensive API documentation for an endpoint.",
            "content": (
                "# API Documentation\n\n"
                "## Objective\n"
                "Document an API endpoint clearly for developers.\n\n"
                "## Template per endpoint\n"
                "### `METHOD /path`\n"
                "**Description**: What this endpoint does.\n\n"
                "**Authentication**: Required scopes.\n\n"
                "**Request**:\n"
                "```json\n"
                '{ "field": "type — description" }\n'
                "```\n\n"
                "**Response** (`status_code`):\n"
                "```json\n"
                '{ "field": "type — description" }\n'
                "```\n\n"
                "**Errors**:\n"
                "| Status | Description |\n"
                "|--------|-------------|\n"
                "| 400 | Bad request |\n"
                "| 404 | Not found |\n\n"
                "**Example**:\n"
                "```bash\n"
                "curl -X POST .../endpoint -H 'Authorization: Bearer TOKEN' -d '{...}'\n"
                "```\n\n"
                "## Steps\n"
                "1. Read the route code to understand request/response shapes.\n"
                "2. Write the documentation following the template.\n"
                "3. Commit to the docs directory.\n"
                "4. Create a PR for review."
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "file_write",
                "git_clone",
                "git_commit_push",
                "github_create_issue",
                "github_comment",
            ],
            "metadata": {"category": "documentation", "complexity": "medium"},
        },
        {
            "name": "user-guide",
            "description": "Write a user guide or tutorial for a product feature.",
            "content": (
                "# User Guide\n\n"
                "## Objective\n"
                "Write a step-by-step guide that helps users accomplish a task.\n\n"
                "## Structure\n"
                '1. **Title** — Action-oriented (e.g., "How to create your first agent")\n'
                "2. **Prerequisites** — What the user needs before starting.\n"
                "3. **Steps** — Numbered, clear instructions with:\n"
                "   - What to do\n"
                "   - What they should see\n"
                "   - Possible issues and solutions\n"
                "4. **Result** — What the user achieves at the end.\n"
                "5. **Next steps** — Related guides or features to explore.\n\n"
                "## Conventions\n"
                '- Use second person ("you")\n'
                "- Include code examples with copy-paste blocks\n"
                "- Keep steps atomic (one action per step)\n"
                "- Test the guide by following it yourself"
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "file_write",
                "git_clone",
                "git_commit_push",
            ],
            "metadata": {"category": "documentation", "complexity": "medium"},
        },
        {
            "name": "changelog-writing",
            "description": "Write release notes and changelog entries.",
            "content": (
                "# Changelog Writing\n\n"
                "## Objective\n"
                "Write clear, user-facing release notes for a new version.\n\n"
                "## Format (Keep a Changelog)\n"
                "```markdown\n"
                "## [version] - YYYY-MM-DD\n\n"
                "### Added\n"
                "- New features.\n\n"
                "### Changed\n"
                "- Changes to existing features.\n\n"
                "### Fixed\n"
                "- Bug fixes.\n\n"
                "### Removed\n"
                "- Deprecated features removed.\n"
                "```\n\n"
                "## Steps\n"
                "1. **Review commits** — List all changes since last release.\n"
                "2. **Categorize** — Group by Added, Changed, Fixed, Removed.\n"
                "3. **Write** — User-facing language, not technical jargon.\n"
                "4. **Highlight** — Call out breaking changes prominently.\n"
                "5. **Commit** — Update CHANGELOG.md and create a PR.\n\n"
                "## Conventions\n"
                "- Start each entry with a verb\n"
                "- Link to relevant issues or PRs\n"
                "- Keep entries concise (one line each)"
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "file_write",
                "git_clone",
                "git_commit_push",
                "github_comment",
            ],
            "metadata": {"category": "documentation", "complexity": "low"},
        },
    ],
    # ── HR Manager ───────────────────────────────────────────────────────
    "hr": [
        {
            "name": "job-posting",
            "description": "Write and prepare a job posting for an open role.",
            "content": (
                "# Job Posting\n\n"
                "## Objective\n"
                "Create an attractive, clear job posting for an open position.\n\n"
                "## Structure\n"
                "1. **Title** — Clear, standard title (avoid internal jargon).\n"
                "2. **About us** — 2-3 sentences about GOABONGA.\n"
                "3. **Role summary** — What this person will do and why it matters.\n"
                "4. **Responsibilities** — 5-7 bullet points.\n"
                "5. **Requirements** — Must-haves (keep it realistic).\n"
                "6. **Nice-to-haves** — Bonus qualifications.\n"
                "7. **Benefits** — Compensation, perks, culture.\n"
                "8. **How to apply** — Clear instructions.\n\n"
                "## Conventions\n"
                "- Use inclusive language\n"
                "- Avoid unnecessary requirements that reduce diversity\n"
                "- Focus on impact, not just tasks"
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "mailler_send_email",
            ],
            "metadata": {"category": "hr", "complexity": "low"},
        },
        {
            "name": "onboarding-plan",
            "description": "Create a structured onboarding plan for a new team member.",
            "content": (
                "# Onboarding Plan\n\n"
                "## Objective\n"
                "Create a 30-60-90 day onboarding plan for a new hire.\n\n"
                "## Week 1: Foundation\n"
                "- Account setup (email, Slack, GitHub, tools)\n"
                "- Meet the team (1:1s with key people)\n"
                "- Read company handbook and architecture docs\n"
                '- Complete first small task ("quick win")\n\n'
                "## Week 2-4: Integration\n"
                "- Shadow team members on real work\n"
                "- Take on first independent task\n"
                "- Attend all team ceremonies\n"
                "- 1:1 with manager: feedback and questions\n\n"
                "## Month 2: Contribution\n"
                "- Own a feature or project independently\n"
                "- Start code reviews\n"
                "- Identify one process improvement\n\n"
                "## Month 3: Ownership\n"
                "- Full velocity on team work\n"
                "- Mentor a newer team member\n"
                "- 90-day review with manager\n\n"
                "## Output\n"
                "Onboarding checklist as tasks and a welcome email."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "mailler_send_email",
                "service_call",
            ],
            "metadata": {"category": "hr", "complexity": "medium"},
        },
        {
            "name": "performance-review",
            "description": "Prepare and conduct a performance review cycle.",
            "content": (
                "# Performance Review\n\n"
                "## Objective\n"
                "Prepare structured performance feedback for a team member.\n\n"
                "## Framework\n"
                "1. **Achievements** — Key accomplishments in the review period.\n"
                "2. **Strengths** — What this person does exceptionally well.\n"
                "3. **Growth areas** — Where they can improve (specific, actionable).\n"
                "4. **Goals** — 2-3 goals for next period (SMART format).\n"
                "5. **Career development** — Skills to build, opportunities to pursue.\n"
                "6. **Rating** — Exceeds / Meets / Below expectations.\n\n"
                "## Steps\n"
                "1. Gather peer feedback and self-assessment.\n"
                "2. Review past goals and OKRs.\n"
                "3. Write the review following the framework.\n"
                "4. Schedule a 1:1 to discuss.\n\n"
                "## Conventions\n"
                "- Be specific (cite examples)\n"
                "- Balance positive and constructive feedback\n"
                "- Focus on behaviors, not personality"
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "service_call",
            ],
            "metadata": {"category": "hr", "complexity": "medium"},
        },
    ],
    # ── Legal Counsel ────────────────────────────────────────────────────
    "legal": [
        {
            "name": "contract-review",
            "description": "Review a contract or agreement for risks and compliance.",
            "content": (
                "# Contract Review\n\n"
                "## Objective\n"
                "Review a contract and identify legal risks or unfavorable terms.\n\n"
                "## Checklist\n"
                "1. **Parties** — Correctly identified, authority to sign.\n"
                "2. **Scope** — Services/deliverables clearly defined.\n"
                "3. **Payment terms** — Amount, schedule, penalties for late payment.\n"
                "4. **Liability** — Limitation of liability, indemnification clauses.\n"
                "5. **IP ownership** — Who owns the work product?\n"
                "6. **Confidentiality** — NDA terms, duration, exceptions.\n"
                "7. **Termination** — Notice period, exit clauses, data return.\n"
                "8. **Data protection** — GDPR compliance, DPA if needed.\n"
                "9. **Governing law** — Jurisdiction and dispute resolution.\n\n"
                "## Output\n"
                "Annotated review with risk flags (High, Medium, Low) and suggested edits."
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "file_write",
            ],
            "metadata": {"category": "legal", "complexity": "high"},
        },
        {
            "name": "compliance-audit",
            "description": "Conduct a GDPR/data protection compliance audit.",
            "content": (
                "# Compliance Audit\n\n"
                "## Objective\n"
                "Audit the platform for GDPR and data protection compliance.\n\n"
                "## Checklist\n"
                "1. **Data inventory** — What personal data do we collect, process, store?\n"
                "2. **Legal basis** — Consent, contract, or legitimate interest for each.\n"
                "3. **Privacy policy** — Accurate, up to date, accessible.\n"
                "4. **User rights** — Access, rectification, deletion, portability implemented.\n"
                "5. **Data retention** — Retention periods defined and enforced.\n"
                "6. **Data processing agreements** — DPAs with all sub-processors.\n"
                "7. **Security measures** — Encryption, access control, breach procedures.\n"
                "8. **Records** — Processing activities documented (ROPA).\n\n"
                "## Output\n"
                "Compliance report with findings and remediation actions."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "file_read",
            ],
            "metadata": {"category": "legal", "complexity": "high"},
        },
        {
            "name": "privacy-policy",
            "description": "Draft or update the platform privacy policy.",
            "content": (
                "# Privacy Policy\n\n"
                "## Objective\n"
                "Draft or update the privacy policy to reflect current data practices.\n\n"
                "## Required sections\n"
                "1. **Data controller** — Company name, contact details, DPO.\n"
                "2. **Data collected** — Types of personal data and how collected.\n"
                "3. **Purpose** — Why we process each type of data.\n"
                "4. **Legal basis** — GDPR article 6 basis for each purpose.\n"
                "5. **Data sharing** — Third parties, sub-processors, transfers.\n"
                "6. **Retention** — How long we keep data.\n"
                "7. **User rights** — How to exercise GDPR rights.\n"
                "8. **Cookies** — Cookie policy and consent mechanism.\n"
                "9. **Changes** — How we notify users of policy changes.\n"
                "10. **Contact** — How to reach us with privacy questions.\n\n"
                "## Output\n"
                "Updated privacy policy as a markdown file. Create a PR for review."
            ),
            "allowed_tools": [
                "search_memory",
                "file_read",
                "file_write",
            ],
            "metadata": {"category": "legal", "complexity": "medium"},
        },
    ],
    # ── Community Manager ────────────────────────────────────────────────
    "community": [
        {
            "name": "event-planning",
            "description": "Plan a community event, webinar, or hackathon.",
            "content": (
                "# Event Planning\n\n"
                "## Objective\n"
                "Plan and organize a community event to drive engagement.\n\n"
                "## Steps\n"
                "1. **Define goal** — Awareness, education, engagement, or leads.\n"
                "2. **Format** — Webinar, workshop, hackathon, AMA, meetup.\n"
                "3. **Content** — Topic, speakers, agenda.\n"
                "4. **Logistics** — Date, platform (Zoom, Discord), registration.\n"
                "5. **Promotion** — Email, social media, community channels.\n"
                "6. **Execute** — Host the event, moderate, record.\n"
                "7. **Follow up** — Send recording, gather feedback, share highlights.\n"
                "8. **Report** — Attendance, engagement, feedback scores.\n\n"
                "## Conventions\n"
                "- Plan at least 2 weeks in advance\n"
                "- Always record for async viewers\n"
                "- Send reminder emails 1 day and 1 hour before"
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "mailler_send_email",
                "mailler_list_templates",
                "service_call",
            ],
            "metadata": {"category": "community", "complexity": "medium"},
        },
        {
            "name": "community-report",
            "description": "Generate a community health report with engagement metrics.",
            "content": (
                "# Community Report\n\n"
                "## Objective\n"
                "Measure and report on community health and engagement.\n\n"
                "## Metrics\n"
                "1. **Growth** — New members this period, total members.\n"
                "2. **Engagement** — Active members, messages, reactions, threads.\n"
                "3. **Content** — Blog views, tutorial completions, docs visits.\n"
                "4. **Events** — Attendance, feedback scores.\n"
                "5. **GitHub** — Stars, forks, issues, PRs from community.\n"
                "6. **Sentiment** — Positive vs negative feedback trends.\n\n"
                "## Steps\n"
                "1. Gather data from analytics, GitHub, and community platforms.\n"
                "2. Compute metrics and compare to previous period.\n"
                "3. Highlight wins and areas of concern.\n"
                "4. Recommend actions to improve engagement.\n\n"
                "## Output\n"
                "Markdown report with metrics tables and recommendations."
            ),
            "allowed_tools": [
                "search_memory",
                "analytics_overview",
                "github_create_issue",
                "github_comment",
            ],
            "metadata": {"category": "community", "complexity": "medium"},
        },
        {
            "name": "content-creation",
            "description": "Create developer-focused content for community channels.",
            "content": (
                "# Content Creation\n\n"
                "## Objective\n"
                "Create engaging content for the developer community.\n\n"
                "## Content types\n"
                "1. **Tutorial** — Step-by-step guide solving a real problem.\n"
                "2. **Blog post** — Thought leadership or technical deep-dive.\n"
                "3. **Social post** — Short, engaging update for Twitter/LinkedIn.\n"
                "4. **Newsletter** — Curated updates for the community.\n"
                "5. **Video script** — Script for a tutorial or demo video.\n\n"
                "## Steps\n"
                "1. **Choose topic** — Based on community questions, trends, or product updates.\n"
                "2. **Research** — Gather technical details and examples.\n"
                "3. **Write** — Follow the content type's format.\n"
                "4. **Review** — Check for accuracy, tone, and brand voice.\n"
                "5. **Publish** — Post to the appropriate channel.\n"
                "6. **Promote** — Share across community platforms.\n\n"
                "## Conventions\n"
                "- Developer-first tone: technical but approachable\n"
                "- Always include working code examples\n"
                "- End with a call to action (try it, join Discord, etc.)"
            ),
            "allowed_tools": [
                "search_memory",
                "http_request",
                "github_create_issue",
                "mailler_send_email",
                "service_call",
            ],
            "metadata": {"category": "community", "complexity": "medium"},
        },
    ],
    # ── Scrum Master ─────────────────────────────────────────────────────
    "scrum_master": [
        {
            "name": "sprint-retrospective",
            "description": "Facilitate a sprint retrospective and capture action items.",
            "content": (
                "# Sprint Retrospective\n\n"
                "## Objective\n"
                "Reflect on the sprint and identify improvements.\n\n"
                "## Format: Start / Stop / Continue\n"
                "1. **Start** — What should we begin doing?\n"
                "2. **Stop** — What should we stop doing?\n"
                "3. **Continue** — What is working well?\n\n"
                "## Steps\n"
                "1. **Review sprint** — Check team status and completed vs planned work.\n"
                "2. **Gather feedback** — Ask each team member for Start/Stop/Continue items.\n"
                "3. **Group themes** — Cluster similar items.\n"
                "4. **Vote** — Identify top 3 items to act on.\n"
                "5. **Action items** — Create specific, assigned tasks for improvements.\n"
                "6. **Document** — Save retro notes to memory for tracking.\n\n"
                "## Metrics to review\n"
                "- Sprint velocity vs plan\n"
                "- Carry-over items\n"
                "- Bug count introduced vs fixed\n"
                "- Sprint goal achieved (yes/no)"
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "team_status",
                "github_create_issue",
            ],
            "metadata": {"category": "agile", "complexity": "medium"},
        },
        {
            "name": "blocker-resolution",
            "description": "Identify and resolve blockers preventing team progress.",
            "content": (
                "# Blocker Resolution\n\n"
                "## Objective\n"
                "Identify, escalate, and resolve blockers for the team.\n\n"
                "## Steps\n"
                "1. **Identify** — Check team status for stalled or blocked tasks.\n"
                "2. **Classify** — Type of blocker:\n"
                "   - Technical: missing API, broken dependency, environment issue\n"
                "   - Process: waiting for approval, unclear requirements\n"
                "   - External: third-party service, vendor response\n"
                "   - Resource: team member unavailable, skill gap\n"
                "3. **Escalate** — If beyond team control, create a task for the appropriate owner.\n"
                "4. **Unblock** — Suggest workarounds or temporary solutions.\n"
                "5. **Track** — Monitor until resolved. Comment on the relevant issue.\n"
                "6. **Prevent** — Identify patterns and address root causes.\n\n"
                "## Output\n"
                "Blocker resolved or escalated with clear ownership and timeline."
            ),
            "allowed_tools": [
                "search_memory",
                "create_task",
                "team_status",
                "github_create_issue",
                "github_comment",
            ],
            "metadata": {"category": "agile", "complexity": "low"},
        },
        {
            "name": "velocity-report",
            "description": "Generate a sprint velocity report with trends.",
            "content": (
                "# Velocity Report\n\n"
                "## Objective\n"
                "Track and report team velocity to improve sprint planning accuracy.\n\n"
                "## Metrics\n"
                "1. **Planned vs completed** — Story points planned vs delivered.\n"
                "2. **Velocity trend** — Last 5 sprints rolling average.\n"
                "3. **Carry-over** — Items not completed, moved to next sprint.\n"
                "4. **Cycle time** — Average time from start to done per item.\n"
                "5. **Throughput** — Number of items completed per sprint.\n\n"
                "## Steps\n"
                "1. Gather data from team status and GitHub issues.\n"
                "2. Compute metrics for the current sprint.\n"
                "3. Compare to historical data from memory.\n"
                "4. Identify trends (accelerating, stable, decelerating).\n"
                "5. Recommend sprint capacity for next sprint.\n\n"
                "## Output\n"
                "Velocity report as markdown table with trend analysis."
            ),
            "allowed_tools": [
                "search_memory",
                "team_status",
                "github_create_issue",
                "github_comment",
                "github_list_runs",
            ],
            "metadata": {"category": "agile", "complexity": "medium"},
        },
    ],
}


def upgrade() -> None:
    conn = op.get_bind()

    # Find goabonga team
    result = conn.execute(
        text("SELECT id FROM teams WHERE slug = :slug"),
        {"slug": TEAM_SLUG},
    )
    row = result.fetchone()
    if not row:
        return
    team_id = str(row[0])

    # For each agent role, look up the agent and insert its skills
    for role, skills in AGENT_SKILLS.items():
        result = conn.execute(
            text("SELECT id FROM agents WHERE team_id = :team_id AND role = :role"),
            {"team_id": team_id, "role": role},
        )
        agent_row = result.fetchone()
        if not agent_row:
            continue
        agent_id = str(agent_row[0])

        for skill in skills:
            conn.execute(
                text(
                    """
                    INSERT INTO skills
                        (id, agent_id, team_id, name, description, content,
                         license, compatibility, metadata, allowed_tools,
                         is_active, created_at, updated_at)
                    VALUES
                        (:id, :agent_id, :team_id, :name, :description, :content,
                         '', '', CAST(:metadata AS jsonb), CAST(:allowed_tools AS jsonb),
                         true, now(), now())
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "agent_id": agent_id,
                    "team_id": team_id,
                    "name": skill["name"],
                    "description": skill["description"],
                    "content": skill["content"],
                    "metadata": json.dumps(skill.get("metadata", {})),
                    "allowed_tools": json.dumps(skill.get("allowed_tools", [])),
                },
            )


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT id FROM teams WHERE slug = :slug"),
        {"slug": TEAM_SLUG},
    )
    row = result.fetchone()
    if row:
        team_id = str(row[0])
        conn.execute(
            text("DELETE FROM skills WHERE team_id = :team_id"),
            {"team_id": team_id},
        )
