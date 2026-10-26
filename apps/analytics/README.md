# analytics

Analytics tracking service for goabonga.com.

This is a member of the `website` uv workspace. All commands are run from the
repository root.

## Run

```bash
uv sync --package analytics
uv run --package analytics uvicorn analytics.main:app --reload --port 8000
```

Settings are read from the environment and from a `.env` file in the working
directory; see `.env.example`.
