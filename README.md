## Vossploee

**Vossploee** is a **unit**: a single **autonomous employee** you can run on its own. It accepts assignments, breaks them into work it can perform, routes pieces to **capabilities** (mail, research, domain-specific workflows, and more), and carries them through to completion—keeping durable state, a full picture of open and finished work, and an HTTP surface for supervision and wiring into other systems.

The same idea scales socially: **many Vossploee units**—each an independent employee with its own skills and mandate—can be **united in a decentralized autonomous organization (DAO)**. The DAO is the collective; each unit remains autonomous, but together they form the **hive** that is the organization.

You can run a unit **on your laptop, a workstation, or any virtual machine** with a normal Python environment. **LLM calls** are configured through Pydantic AI model ids and provider credentials: use **public APIs** (OpenAI, Anthropic, Google, and others supported by your stack) or **private / self-hosted** endpoints, depending on policy and networking.

**Vossploee behaves in a non-deterministic way**: planning and execution are model-guided, so runs are not fixed scripts with identical outcomes every time. The concrete surface area for acting in the world is **tools**—defined ways to read, edit, call external systems, or otherwise perform an action. Tools are **grouped into capabilities**. Each **capability** bundles its own slice of behavior: **agent implementations** that follow the framework’s interfaces, **specialized prompts**, **tools** wired to external APIs where needed, and **supporting data** (configuration, allowlists, and similar) that keeps that domain coherent.

## Technologies

- **Python** 3.12+
- **[FastAPI](https://fastapi.tiangolo.com/)** — HTTP API
- **[Uvicorn](https://www.uvicorn.org/)** — ASGI server
- **[Pydantic](https://docs.pydantic.dev/)** & **[Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)** — configuration and models
- **[Pydantic AI](https://ai.pydantic.dev/)** — structured LLM agents (decomposer, architect, implementer, capability agents)
- **[aiosqlite](https://github.com/omnilib/aiosqlite)** — async SQLite
- **SQLite** — durable task state and logs
- **[uv](https://docs.astral.sh/uv/)** — project and lockfile (`uv.lock`)

## What Is In This Repo

- HTTP API and lifespan in `src/vossploee/main.py` (**`X-API-KEY`** / `VOSSPLOEE_API_KEY` — set a shared secret in `.env`, e.g. from `default.env`; leave empty only if you deliberately want no HTTP key check)
- SQLite-backed task repository, workers, and agent registry
- **Capability** packages under `src/vossploee/capabilities/` (pluggable tools + config)
- Shared tool registry in `src/vossploee/tools/registry.py`

Current capability packages:

- **`core`** — turns requests into concrete actions and executes them (includes `core.imap`)
- **`brainstormer`** — generates idea branches and short strategy briefs

Additional capability packages can be dropped into `src/vossploee/capabilities/` (each with its own `config.toml`, `README.md`, and `tools_register`) and enabled via `VOSSPLOEE_ENABLED_CAPABILITIES`. This is how a unit takes on new domain skills—for example, a **multi-omics EHR worker** that assembles a synthetic cohort for a downstream study.

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
- `VOSSPLOEE_AGENT_MODEL` (for real model runs — public or private provider, depending on the model id and env)
- provider keys (for example `OPENAI_API_KEY` when using a hosted model)
- `VOSSPLOEE_API_KEY` — after copying `default.env`, your `.env` includes an example shared secret; clients must send matching `X-API-KEY` (clear the value in `.env` only if you fully trust network isolation; not recommended for exposed hosts)
- capability credentials as needed (for example IMAP/SMTP for the `core` mail tool)

4. Run the API:

```bash
uv run python -m uvicorn vossploee.main:app --reload
```

Health check over **HTTPS** in front of nginx (send `X-API-KEY` unless you have explicitly disabled HTTP key checks; use your `PUBLIC_HOST` if it differs):

```bash
curl -H "X-API-KEY: <your-key>" http://127.0.0.1:8000/health
```

Local uvicorn without a TLS terminator listens on `http://127.0.0.1:8000` only.

## API

Base prefix defaults to `/api` (configurable via `VOSSPLOEE_API_PREFIX`).

- `POST /api/tasks` — submit a description; decomposer creates queue01 root tasks routed to capabilities
- `GET /api/tasks` — full task tree
- `GET /api/tasklog` — all archived completed workflows
- `GET /api/log?offset=0&limit=10` — paginated archived workflows (newest first)
- `GET /api/capabilities` — metadata for enabled capabilities
- `DELETE /api/tasks/{task_id}` — delete task subtree
- `GET /health` — service health

Example — ask the unit to build a small synthetic cohort (assumes a multi-omics/EHR capability is enabled):

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: <your-key>" \
  -d '{
    "description": "Populate 20 synthetic EHRs for a COVID-19 cohort aged 70+, each with demographics, comorbidities, hospitalization timeline, and a matching multi-omics summary (genomics, transcriptomics, proteomics). Store them as individual records and send me a short cohort summary by email."
  }'
```

## Configuration

Main settings (`.env`, prefix `VOSSPLOEE_`):

- `VOSSPLOEE_APP_NAME` (default: `Vossploee Task Orchestrator`)
- `VOSSPLOEE_DATABASE_PATH` (default: `data/tasks.db`)
- `VOSSPLOEE_POLL_INTERVAL_SECONDS` (default: `1`)
- `VOSSPLOEE_API_PREFIX` (default: `/api`)
- `VOSSPLOEE_API_KEY` — when set (see `default.env` after `cp` to `.env`), every request must send `X-API-KEY` (401/403 otherwise). Set **empty** in `.env` only to skip HTTP key checks on tightly isolated networks. Rotate the example value for production.
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

## Tests

```bash
uv run pytest
```
