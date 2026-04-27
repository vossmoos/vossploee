## Vossploee

Vossploee is a framework for building autonomous AI-workers: focused AI-agents that can receive work, reason about it, use tools, execute tasks, remember their context, and delegate work to other agents.

It is designed as a practical brick for AI-driven autonomous agent networks. A single Vossployee can run as an autonomous worker process. Multiple Vossployees can be combined into a network of specialized workers, each with its own capabilities, roles, channels, memory, and operational boundaries. The result is a foundation for engineered agentic systems that can decompose work, execute tasks, communicate with users, and evolve into larger autonomous organizations.

## Why It Matters

Modern AI automation needs more than a prompt and an API call. Real autonomous workers need structure:

- **Roles** focus on a particular responsibility, behavior, and tool access.
- **Capabilities** package domain-specific skills that can be enabled, disabled, or extended.
- **Channels** connect workers to the outside world through email, messengers, REST, or future interfaces.
- **Tasks** provide a durable contract for decomposition, execution, cancellation, and inspection.
- **Memory** gives workers long-term context instead of stateless one-off responses.
- **Reasoning telemetry** makes agent decisions easier to inspect and improve.

This makes Vossploee useful both as a working implementation and as an architectural pattern for teams building autonomous AI-worker networks.

## Core Idea

Each worker is composed from three explicit building blocks:

- `capability`: what the worker knows how to do.
- `role`: what responsibility (focus) the worker has inside that capability.
- `channel`: how work enters and leaves the system.

Together they form `capability.role` workers such as `core.decomposer`, `core.executor`, or `haiku.writer`. This model keeps the system modular while allowing many workers to cooperate inside a larger network.

## Markdown-Configurable Agent Identity

Vossploee keeps agent instructions close to the code, but editable by humans. The global worker identity is defined in `src/vossploee/WHOAMI.md`, and each capability can define its own behavior contract in a local `WHOAMI.md`, for example `src/vossploee/capabilities/core/WHOAMI.md`.

At runtime, Vossploee composes these Markdown instructions with the selected role prompt. This means the personality, operating principles, domain focus, and capability-specific rules of an AI-worker can be changed by editing plain `.md` files, without rebuilding the framework or hard-coding prompts into business logic.

## Current Architecture

- Runtime entrypoint: `src/vossploee/main.py`
- Settings: `src/vossploee/config.py` (`VOSSPLOEE_` env prefix)
- Storage:
  - `tasks` (flat durable queue)
  - `tasklog` (archived completed roots)
  - `channel_messages` (inbound/outbound history)
  - `reasoning` (confidence + explanation records)
- Worker loop: one async loop per `role_id`
- Tool registry: capability-owned tool registration

## Active Capabilities

- `core`
  - `core.decomposer` (entrypoint decomposer by default)
  - `core.executor`
- `haiku` (test capability)
  - `haiku.writer`

## Active Channels

- `email` (default channel scaffold with message persistence + API surface)
- `telegram` (LLM gatekeeper; chats with user and invokes decomposer only for explicit tasks)
- `rest` (non-AI ingress channel that forwards directly to decomposer)

## Quick Start

1. Install dependencies:

```bash
uv sync
```

2. Create local env:

```bash
cp default.env .env
```

3. Configure at least:

- `VOSSPLOEE_API_KEY`
- `VOSSPLOEE_AGENT_MODEL`
- `OPENAI_API_KEY` or `VOSSPLOEE_OPENAI_API_KEY` (if using hosted LLM/embeddings)

Optional but important:

- `VOSSPLOEE_ENTRYPOINT_DECOMPOSER` (default `core.decomposer`)
- `VOSSPLOEE_ENABLED_CAPABILITIES` (default currently starts with `core`)
- `VOSSPLOEE_ENABLED_CHANNELS` (default includes `email,rest,telegram`)
- `VOSSPLOEE_REASONING_LOG_ENABLED` (`false` by default)
- `VOSSPLOEE_MEMORY_INJECT_TOP_K` (default `6`)
- email allowlist and SMTP/IMAP env vars:
  - `VOSSPLOEE_CHANNEL_EMAIL_ALLOWED_SENDERS`
  - `VOSSPLOEE_CHANNEL_EMAIL_USER_ENV`
  - `VOSSPLOEE_CHANNEL_EMAIL_PASSWORD_ENV`

4. Run API:

```bash
uv run python -m uvicorn vossploee.main:app --reload
```

5. Health check:

```bash
curl -H "X-API-KEY: <your-key>" http://127.0.0.1:8000/health
```

## API

Base prefix: `/api` (configurable via `VOSSPLOEE_API_PREFIX`).

- `POST /api/channels/rest/inbound`
- `GET /api/tasks`
- `GET /api/log?offset=&limit=`
- `DELETE /api/tasks/{task_id}`
- `GET /api/capabilities`
- `GET /api/channels`
- `GET /api/channels/email/messages?user=<user_id>&n=50`
- `POST /api/channels/email/poll`
- `GET /api/channels/telegram/messages?user=<user_id>&n=50`
- `POST /api/channels/telegram/poll`

## Long-Term Memory

- Memory store uses Chroma path from `VOSSPLOEE_CHROMA_PATH` (default `data/chroma`).
- Memory context is auto-injected into role LLM calls.
- Explicit tools:
  - `core.memory_remember`
  - `core.memory_recall`

## Notes

- `v0.1.0.instruction.md` is restored and kept as architecture source-of-truth.
- Legacy capabilities/tests/docs were intentionally removed during cleanup.
