## Vossploee

**AI-Agent Framework for Distributed Autonomous Organizations**

The goal is a **base for building autonomous virtual multifunctional employees**—capable agents you can assemble into **Distributed Autonomous Organizations (DAOs)** so coordinated, decentralized teams of agents can own and execute work end to end.

This repository implements that foundation as a FastAPI + SQLite **task orchestrator**: the **decomposer** normalizes each incoming task, **routes it to a capability namespace**, then that capability’s **architect** and **implementer** workers process queue01 → queue02 in parallel with other capabilities.

### Run

uv keeps the project virtualenv in **`.venv`** at the repo root (uv default, same idea as PEP 405). Prefer `uv run` so that environment is used; if you `source .venv/bin/activate`, do it only from this **`vossploee`** tree (not an old copy), or `uv` will warn when `VIRTUAL_ENV` does not match.

```bash
uv run python -m uvicorn vossploee.main:app --reload
```

### API

- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/capabilities` — enabled capabilities with README-derived metadata
- `DELETE /api/tasks/{task_id}`
- `GET /health`

Example request:

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Create orchestration service",
    "description": "Accept business tasks, queue them, split them into Gherkin technical tasks, and run the implementation worker."
  }'
```

### Configuration

Environment variables:

- `VOSSPLOEE_DATABASE_PATH=data/tasks.db`
- `VOSSPLOEE_POLL_INTERVAL_SECONDS=1`
- `VOSSPLOEE_AGENT_MODEL=openai:gpt-4.1-mini`
- `VOSSPLOEE_ENABLED_CAPABILITIES=` — comma-separated capability ids, or **empty** to enable every package under `src/vossploee/capabilities/`

`VOSSPLOEE_AGENT_MODEL` is required for real task processing. If it is missing or the model call fails, the agent methods raise an error instead of falling back to synthetic output.

### Capability modules

Each capability is a folder `src/vossploee/capabilities/<name>/` exporting `build_capability(settings)` and a short `README.md` (description + functionality) used by the decomposer and by `GET /api/capabilities`.

Parallel capabilities run together: workers are namespaced by `capability_name` on each task so queue01/queue02 items are only handled by the matching capability’s architect/implementer.

The **decomposer** picks the best capability id from the **enabled** set using the README catalog; if the model returns an unknown id, it falls back to the first enabled capability.
