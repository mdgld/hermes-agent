# Tech Stack

## Language & Runtime
- **Python 3.11–3.13** (capped at `<3.14` — Rust-backed transitives lack cp314 wheels)
- **TypeScript/Node** for `ui-tui/` and some plugins (e.g. `plugins/todoist-mcp/`)

## Package Management
- **uv** — lock file at `uv.lock`, used for all installs and venv management
- Venvs: `.venv/` (primary), `venv/` (legacy), `.notebooklm-cli-venv/` (optional tool)
- Install dev extras: `uv sync --extra dev`

## Build
- **setuptools >= 77** (PEP 639 SPDX license form requires this floor)
- `pyproject.toml`-based, no `setup.py`

## Key dev dependencies (exact pins)
- `pytest==9.0.2` + `pytest-asyncio==1.3.0`
- `ruff==0.15.10` — linter + formatter
- `ty==0.0.21` — type checker (NOT mypy)
- `mcp==1.26.0` — for MCP-related tests

## Core runtime dependencies (selected)
- `openai==2.24.0` — primary SDK (used for all providers via openai-compat APIs)
- `pydantic==2.13.4`
- `httpx[socks]==0.28.1`
- `rich==14.3.3`
- `prompt_toolkit==3.0.52`
- `ruamel.yaml==0.18.17` (config files)
- `croniter==6.0.0` (scheduled jobs)

## Optional extras
Provider-specific packages (`anthropic`, `firecrawl-py`, `exa-py`, etc.) are NOT in `dependencies` — they live in extras and are lazy-installed via `tools/lazy_deps.py` at runtime.
