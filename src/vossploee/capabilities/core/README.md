# Core

## Description

Turn a business request into concrete **doable actions**, then **execute** them—not limited to software or code.

## Functionality

The **Planner** (queue01) understands the ask and decomposes it into queue02 items: each item is one clear action the **Implementer** can perform (e.g. send an email, produce text, validate something). Prefer one queue02 task when a single step suffices. The **Implementer** actually carries out each action and returns a summary plus a real **artifact** (what was produced or done).

Baseline tools (see `config.toml`, e.g. `core.imap`) register pydantic-ai tools for this capability and can be reused from other capabilities by listing the same qualified id. The `core.imap` tool sends email via SMTP using `[imap]` in this file; set credential env var names from `[imap]` in `.env`.
