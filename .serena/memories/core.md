# hermes-agent — Core Source Map

**Project**: hermes-agent v0.16.0 by Nous Research — self-improving AI agent CLI.
**Repo root**: `/Users/matthewgold/.hermes/hermes-agent/`

## Top-level layout

| Path | Purpose |
|------|---------|
| `hermes_cli/` | CLI layer — `main.py` is the 11k-line monolith entry point |
| `hermes_cli/_parser.py` | Argument parser (split from main for Termux fast-path) |
| `agent/` | Core agent logic, transports (bedrock, codex, openai, responses) |
| `agent/transports/` | Provider-specific transport adapters (bedrock, codex, etc.) |
| `gateway/` | Gateway/proxy server for multi-client deployments |
| `tools/` | Tool implementations (file, shell, search, send_message, etc.) |
| `plugins/` | Plugin system loader and bundled plugins |
| `skills/` | Skills hub (loaded at runtime) |
| `optional-skills/` | Skills not bundled by default |
| `tests/` | pytest test suite (unit + integration-marked) |
| `apps/` | Auxiliary apps (ACP adapter, etc.) |
| `web/` / `website/` | Web UI source |
| `ui-tui/` | TUI frontend (TypeScript/Node, built separately) |
| `tui_gateway/` | Thin Python bridge to TUI Node process |

## Key entry points

- **CLI**: `hermes_cli/main.py` → `main()` — registered as `hermes` console script
- **Chat**: `cmd_chat` dispatches to `agent/` transports
- **Termux fast paths**: `_try_termux_fast_cli_launch` / `_try_termux_fast_tui_launch` bypass full parser

## Important invariants

- All production deps are **exact-pinned** (`==X.Y.Z`) in pyproject.toml — no ranges. See rationale in pyproject.toml (supply-chain attack defense).
- Lazy imports throughout CLI: feature modules are imported inside their `cmd_*` functions, not at top of `main.py`.
- `hermes_cli/main.py` is intentionally a monolith; don't split it without understanding the Termux fast-path constraints.

## Further memories

- Tech stack / tooling: `mem:tech_stack`
- Dev/test/lint commands: `mem:suggested_commands`
- Code conventions: `mem:conventions`
- Task completion checklist: `mem:task_completion`
