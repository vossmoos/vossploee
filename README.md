## Vossploee

FastAPI + SQLite task orchestrator for multi-capability AI workers.

The app accepts a business request, decomposes it into queue01 root tasks, routes each root to a capability namespace, and runs architect/implementer workers that process queue01 -> queue02.

## What Is In This Repo

- HTTP API with background workers in `src/vossploee/main.py`
- SQLite-backed task state and archived logs
- Capability system under `src/vossploee/capabilities/`
- Shared tool registry in `src/vossploee/tools/registry.py`

Current capability packages:

- `core` - turns requests into concrete actions and executes them (includes `core.imap`)
- `brainstormer` - generates idea branches and short strategy briefs
- `upworkmanager` - searches recent Upwork jobs, filters/triages, and sends matched jobs by email

## Quick Start

1. Install dependencies:

```bash
uv sync
```

2. Create local env:

```bash
cp default.env .env
```

3. Fill required values in `.env`:
- `VOSSPLOEE_AGENT_MODEL` (for real model runs)
- provider keys (for example `OPENAI_API_KEY`)
- capability credentials as needed (for example IMAP/SMTP and Upwork)

4. Run the API:

```bash
uv run python -m uvicorn vossploee.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## API

Base prefix defaults to `/api` (configurable via `VOSSPLOEE_API_PREFIX`).

- `POST /api/tasks` - decompose request and create queue01 roots
- `GET /api/tasks` - full task tree
- `GET /api/tasklog` - all archived completed workflows
- `GET /api/log?offset=0&limit=10` - paginated archived workflows (newest first)
- `GET /api/capabilities` - metadata for enabled capabilities
- `DELETE /api/tasks/{task_id}` - delete task subtree
- `GET /health` - service health

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Check for new Upwork AI-agent jobs in the last hour and email top matches."
  }'
```

## Configuration

Main settings (`.env`, prefix `VOSSPLOEE_`):

- `VOSSPLOEE_APP_NAME` (default: `Vossploee Task Orchestrator`)
- `VOSSPLOEE_DATABASE_PATH` (default: `data/tasks.db`)
- `VOSSPLOEE_POLL_INTERVAL_SECONDS` (default: `1`)
- `VOSSPLOEE_API_PREFIX` (default: `/api`)
- `VOSSPLOEE_MAX_DECOMPOSED_ROOTS` (default: `168`)
- `VOSSPLOEE_AGENT_MODEL` (required for real runs; use `test` for offline/CI-style runs)
- `VOSSPLOEE_ENABLED_CAPABILITIES` (comma-separated ids, or empty for all discovered capabilities)

Notes:

- `.env` is loaded into process env so capability tools can read credentials from `os.getenv`.
- `OPENAI_API_KEY` can be set directly, or via `VOSSPLOEE_OPENAI_API_KEY`.

## Capability Model

Each capability package exports `build_capability(settings)` and has a `README.md` used by:

- decomposer capability routing context
- `GET /api/capabilities` response

On startup, the app:

- discovers capability packages under `src/vossploee/capabilities/`
- validates `VOSSPLOEE_ENABLED_CAPABILITIES` against discovered ids
- imports per-capability `tools_register` modules
- validates capability `config.toml` tool allowlists against the global tool registry

## Utility Scripts

- `uv run python uw_oauth.py` - one-time Upwork OAuth helper (prints env lines for refresh/access token setup)
- `uv run python uw_calibrate.py` - run Upwork search defaults and inspect pre-AI filter counts

## Tests

```bash
uv run pytest
```
