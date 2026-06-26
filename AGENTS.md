# Hermes Agent - Development Guide

Instructions for AI coding assistants and developers working on the hermes-agent codebase.

**Contributor-only sections** (PR policies, dependency rules, skill authoring standards, TUI/desktop deep-dives, testing internals) live in **`CONTRIBUTING.md`** so this file stays compact.

**Never give up on the right solution.**

## What Hermes Is

Hermes is a personal AI agent that runs the same agent core across a CLI, messaging gateway (Telegram, Discord, Slack, ~20 other platforms), TUI, and Electron desktop app. It learns across sessions (memory + skills), delegates to subagents, runs scheduled jobs, and drives a real terminal and browser. Extended primarily through **plugins and skills**, not by growing the core.

Two properties shape almost every design decision:

- **Per-conversation prompt caching is sacred.** Anything that mutates past context, swaps toolsets, or rebuilds the system prompt mid-conversation invalidates the cache and multiplies cost. The ONLY exception is context compression.
- **The core is a narrow waist; capability lives at the edges.** Every model tool added is sent on every API call. New capability arrives as CLI command + skill, service-gated tool (`check_fn`), or plugin — not as core surface.

## Development Environment

```bash
source .venv/bin/activate   # or: source venv/bin/activate
```

`scripts/run_tests.sh` probes `.venv` first, then `venv`, then `$HOME/.hermes/hermes-agent/venv` (for worktrees that share a venv with the main checkout).

## Project Structure

File counts shift constantly — don't treat the tree below as exhaustive. The notes call out the load-bearing entry points you'll actually edit.

```
hermes-agent/
├── run_agent.py          # AIAgent class — core conversation loop (~12k LOC)
├── model_tools.py        # Tool orchestration, discover_builtin_tools(), handle_function_call()
├── toolsets.py           # Toolset definitions, _HERMES_CORE_TOOLS list
├── cli.py                # HermesCLI class — interactive CLI orchestrator (~11k LOC)
├── hermes_state.py       # SessionDB — SQLite session store (FTS5 search)
├── hermes_constants.py   # get_hermes_home(), display_hermes_home() — profile-aware paths
├── hermes_logging.py     # setup_logging() — agent.log / errors.log / gateway.log
├── batch_runner.py       # Parallel batch processing
├── agent/                # Agent internals (provider adapters, memory, caching, compression)
├── hermes_cli/           # CLI subcommands, setup wizard, plugins loader, skin engine
├── tools/                # Tool implementations — auto-discovered via tools/registry.py
│   └── environments/     # Terminal backends (local, docker, ssh, modal, daytona, singularity)
├── gateway/              # Messaging gateway — run.py + session.py + platforms/
│   ├── platforms/        # Adapter per platform (telegram, discord, slack, whatsapp,
│   │                     #   homeassistant, signal, matrix, mattermost, email, sms,
│   │                     #   dingtalk, wecom, weixin, feishu, qqbot, bluebubbles,
│   │                     #   yuanbao, webhook, api_server, ...). See ADDING_A_PLATFORM.md.
│   └── builtin_hooks/    # Extension point for always-registered gateway hooks
├── plugins/              # Plugin system
│   ├── memory/           # Memory-provider plugins (honcho, mem0, supermemory, ...)
│   ├── context_engine/   # Context-engine plugins
│   ├── model-providers/  # Inference backend plugins (openrouter, anthropic, gmi, ...)
│   ├── kanban/           # Multi-agent board dispatcher + worker plugin
│   ├── observability/    # Metrics / traces / logs plugin
│   ├── image_gen/        # Image-generation providers
│   └── <others>/         # disk-cleanup, google_meet, platforms, spotify, ...
├── optional-skills/      # Heavier/niche skills shipped but NOT active by default
├── skills/               # Built-in skills bundled with the repo
├── ui-tui/               # Ink (React) terminal UI — `hermes --tui`
│   └── src/              # entry.tsx, app.tsx, gatewayClient.ts + app/components/hooks/lib
├── tui_gateway/          # Python JSON-RPC backend for the TUI
├── acp_adapter/          # ACP server (VS Code / Zed / JetBrains integration)
├── cron/                 # Scheduler — jobs.py, scheduler.py
├── scripts/              # run_tests.sh, release.py, auxiliary scripts
├── website/              # Docusaurus docs site
└── tests/                # Pytest suite (~17k tests across ~900 files as of May 2026)
```

**User config:** `~/.hermes/config.yaml` (settings), `~/.hermes/.env` (API keys only).
**Logs:** `~/.hermes/logs/` — `agent.log` (INFO+), `errors.log` (WARNING+), `gateway.log` when running the gateway. Profile-aware via `get_hermes_home()`. Browse with `hermes logs [--follow] [--level ...] [--session ...]`.

## TypeScript Style

Applies to TypeScript across Hermes: desktop, TUI, website, and future TS packages.

- Prefer small nanostores over component state when state is shared, reused, or read by distant UI.
- Let each feature own its atoms. Chat state belongs near chat, shell state near shell, shared state in `src/store`.
- Components that render from an atom should use `useStore`. Non-rendering actions should read with `$atom.get()`.
- Do not pass state through three components when the leaf can subscribe to the atom.
- No monolithic hooks. A hook should own one narrow job. Prefer colocated action modules over hidden god hooks.
- If a callback is pure side effect, use the terse void form: `onState={st => void setGatewayState(st)}`.
- Async UI handlers: `onClick={() => void save()}`.
- Prefer interfaces for public props and shared object shapes. Avoid `type X = { ... }` for object props.
- Extend React primitives: `React.ComponentProps<'button'>`, `Omit<...>`, `Pick<...>`.
- Table-driven beats condition ladders when mapping ids, routes, or views.
- `src/app` owns routes, pages, and page-specific components. `src/store` owns shared atoms. `src/lib` owns shared pure helpers.

## File Dependency Chain

```
tools/registry.py  (no deps — imported by all tool files)
       ↑
tools/*.py  (each calls registry.register() at import time)
       ↑
model_tools.py  (imports tools/registry + triggers tool discovery)
       ↑
run_agent.py, cli.py, batch_runner.py, environments/
```

---

## AIAgent Class (run_agent.py)

The real `AIAgent.__init__` takes ~60 parameters. The minimum subset you'll usually touch:

```python
class AIAgent:
    def __init__(self,
        base_url: str = None,
        api_key: str = None,
        provider: str = None,
        api_mode: str = None,              # "chat_completions" | "codex_responses" | ...
        model: str = "",                   # empty → resolved from config/provider later
        max_iterations: int = 90,          # tool-calling iterations (shared with subagents)
        enabled_toolsets: list = None,
        disabled_toolsets: list = None,
        quiet_mode: bool = False,
        save_trajectories: bool = False,
        platform: str = None,              # "cli", "telegram", etc.
        session_id: str = None,
        skip_context_files: bool = False,
        skip_memory: bool = False,
        credential_pool=None,
        # ... plus callbacks, thread/user/chat IDs, iteration_budget, fallback_model,
        # checkpoints config, prefill_messages, service_tier, reasoning_config, etc.
    ): ...

    def chat(self, message: str) -> str:
        """Simple interface — returns final response string."""

    def run_conversation(self, user_message: str, system_message: str = None,
                         conversation_history: list = None, task_id: str = None) -> dict:
        """Full interface — returns dict with final_response + messages."""
```

### Agent Loop

The core loop inside `run_conversation()` — entirely synchronous, with interrupt checks, budget tracking, and a one-turn grace call:

```python
while (api_call_count < self.max_iterations and self.iteration_budget.remaining > 0) \
        or self._budget_grace_call:
    if self._interrupt_requested: break
    response = client.chat.completions.create(model=model, messages=messages, tools=tool_schemas)
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = handle_function_call(tool_call.name, tool_call.args, task_id)
            messages.append(tool_result_message(result))
        api_call_count += 1
    else:
        return response.content
```

Messages follow OpenAI format: `{"role": "system/user/assistant/tool", ...}`. Reasoning content is stored in `assistant_msg["reasoning"]`.

---

## CLI Architecture (cli.py)

- **Rich** for banner/panels, **prompt_toolkit** for input with autocomplete
- **KawaiiSpinner** (`agent/display.py`) — animated faces during API calls, `┊` activity feed for tool results
- `load_cli_config()` merges hardcoded defaults + user config YAML
- **Skin engine** (`hermes_cli/skin_engine.py`) — data-driven CLI theming; initialized from `display.skin` config key at startup
- Skill slash commands: `agent/skill_commands.py` scans `~/.hermes/skills/`, injects as **user message** (not system prompt) to preserve prompt caching

### Slash Command Registry (`hermes_cli/commands.py`)

All slash commands are defined in a central `COMMAND_REGISTRY` list of `CommandDef` objects. Every downstream consumer derives from this registry automatically: CLI dispatch, gateway, Telegram BotCommand menu, Slack subcommand routing, autocomplete, CLI help.

### Adding a Slash Command

1. Add a `CommandDef` entry to `COMMAND_REGISTRY` in `hermes_cli/commands.py`:
```python
CommandDef("mycommand", "Description of what it does", "Session",
           aliases=("mc",), args_hint="[arg]"),
```
2. Add handler in `HermesCLI.process_command()` in `cli.py`.
3. If the command is available in the gateway, add a handler in `gateway/run.py`.
4. For persistent settings, use `save_config_value()` in `cli.py`.

**`CommandDef` fields:** `name`, `description`, `category` (Session/Configuration/Tools & Skills/Info/Exit), `aliases`, `args_hint`, `cli_only`, `gateway_only`, `gateway_config_gate` (config dotpath that enables a `cli_only` command in the gateway when truthy).

---

## TUI Architecture (ui-tui + tui_gateway)

Activated via `hermes --tui` or `HERMES_TUI=1`.

```
hermes --tui
  └─ Node (Ink)  ──stdio JSON-RPC──  Python (tui_gateway)
       │                                  └─ AIAgent + tools + sessions
       └─ renders transcript, composer, prompts, activity
```

TypeScript owns the screen. Python owns sessions, tools, model calls, and slash command logic. Transport: newline-delimited JSON-RPC over stdio. See `tui_gateway/server.py` for the full method/event catalog.

**Do not re-implement the primary chat experience in React.** The main transcript, composer/input flow, and PTY-backed terminal belong to the embedded `hermes --tui` — extend Ink instead. Structured React UI around the TUI (sidebars, inspectors, status panels) is fine when it complements rather than replaces.

### Electron Desktop App (`apps/desktop/`)

Separate from both the classic CLI and the dashboard's embedded TUI. Electron + React + nanostore + `@assistant-ui/react` talking to `tui_gateway` over JSON-RPC. Slash commands curated via `apps/desktop/src/lib/desktop-slash-commands.ts`. See CONTRIBUTING.md for the full slash pipeline and curation rules. Route desktop bugs to the `hermes-desktop-app-work` skill.

---

## Adding New Tools

Settle the footprint question first (see "The Footprint Ladder" in CONTRIBUTING.md): most capabilities should NOT be core tools. For custom or local-only tools, use the plugin route: `~/.hermes/plugins/<name>/plugin.yaml` + `__init__.py`, register with `ctx.register_tool(...)`.

Built-in/core tools require changes in **2 files**:

**1. Create `tools/your_tool.py`:**
```python
import json, os
from tools.registry import registry

def check_requirements() -> bool:
    return bool(os.getenv("EXAMPLE_API_KEY"))

def example_tool(param: str, task_id: str = None) -> str:
    return json.dumps({"success": True, "data": "..."})

registry.register(
    name="example_tool",
    toolset="example",
    schema={"name": "example_tool", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: example_tool(param=args.get("param", ""), task_id=kw.get("task_id")),
    check_fn=check_requirements,
    requires_env=["EXAMPLE_API_KEY"],
)
```

**2. Add to `toolsets.py`** — either `_HERMES_CORE_TOOLS` (all platforms) or a new toolset. **This step is required:** auto-discovery imports the tool but does NOT expose it until its name appears in a toolset.

- **Path references in schema descriptions:** use `display_hermes_home()` for profile-aware paths.
- **State files:** use `get_hermes_home()`, never `Path.home() / ".hermes"`.
- **Agent-level tools** (todo, memory): intercepted by `run_agent.py` before `handle_function_call()`. See `tools/todo_tool.py`.

---

## Adding Configuration

### config.yaml options:
1. Add to `DEFAULT_CONFIG` in `hermes_cli/config.py`.
2. Bump `_config_version` ONLY if you need to actively migrate/transform existing user config (renaming keys, changing structure). Adding a new key to an existing section is handled by deep-merge and does NOT require a version bump.

### Top-level `config.yaml` sections (non-exhaustive):

`model`, `agent`, `terminal`, `compression`, `display`, `stt`, `tts`, `memory`, `security`, `delegation`, `smart_model_routing`, `checkpoints`, `auxiliary`, `curator`, `skills`, `gateway`, `logging`, `cron`, `profiles`, `plugins`, `honcho`.

`auxiliary` holds per-task overrides for side-LLM work (curator, vision, embedding, title generation, etc.) — each task can pin its own provider/model/base_url/max_tokens/reasoning_effort. See `agent/auxiliary_client.py::_resolve_auto` for resolution order.

### Config loaders (three paths — know which one you're in):

| Loader | Used by | Location |
|--------|---------|----------|
| `load_cli_config()` | CLI mode | `cli.py` — merges CLI-specific defaults + user YAML |
| `load_config()` | `hermes tools`, `hermes setup`, most CLI subcommands | `hermes_cli/config.py` |
| Direct YAML load | Gateway runtime | `gateway/run.py` + `gateway/config.py` |

If you add a new key and the CLI sees it but the gateway doesn't (or vice versa), you're on the wrong loader. Check `DEFAULT_CONFIG` coverage.

### Working directory:
- **CLI** — `os.getcwd()`.
- **Messaging** — `terminal.cwd` from `config.yaml`, bridged to `TERMINAL_CWD` env var. `MESSAGING_CWD` has been removed; `TERMINAL_CWD` in `.env` is deprecated.

### .env variables (SECRETS ONLY — API keys, tokens, passwords):
Add to `OPTIONAL_ENV_VARS` in `hermes_cli/config.py`. Non-secret settings (timeouts, thresholds, feature flags, paths) belong in `config.yaml`, not `.env`.

---

## Skin/Theme System

Skins are **pure data** — no code changes needed. Built-in skins live in `hermes_cli/skin_engine.py`; user skins at `~/.hermes/skins/*.yaml`. Missing values inherit from the `default` skin. Activate with `/skin <name>` or `display.skin: <name>`. Built-in skins: `default`, `ares`, `mono`, `slate`.

See CONTRIBUTING.md for the full skin authoring format (built-in dict structure + user YAML format + what each key customizes).

---

## Plugins

Two plugin surfaces:

### General plugins (`hermes_cli/plugins.py` + `plugins/<name>/`)

`PluginManager` discovers from `~/.hermes/plugins/`, `./.hermes/plugins/`, and pip entry points. Each plugin exposes `register(ctx)` to add lifecycle hooks (`pre_tool_call`, `post_tool_call`, `pre_llm_call`, `post_llm_call`, `on_session_start`, `on_session_end`), new tools (`ctx.register_tool(...)`), and CLI subcommands (`ctx.register_cli_command(...)`). **Discovery pitfall:** `discover_plugins()` only runs as a side effect of importing `model_tools.py` — call it explicitly for code paths that don't import `model_tools.py` first.

**Rule (May 2026):** plugins MUST NOT modify core files. If a plugin needs a capability, expand the generic plugin surface — never hardcode plugin-specific logic into core.

### Memory-provider plugins (`plugins/memory/<name>/`)

Separate discovery system. Implements `MemoryProvider` ABC (`agent/memory_provider.py`), orchestrated by `agent/memory_manager.py`. Lifecycle hooks: `sync_turn()`, `prefetch()`, `shutdown()`, optional `post_setup()`. **No new in-tree memory providers (May 2026)** — new backends must ship as standalone plugin repos.

### Model-provider plugins (`plugins/model-providers/<name>/`)

Lazy, separate discovery system — scanned on first `get_provider_profile()` or `list_providers()` call. User plugins of the same name override bundled ones (last-writer-wins). Full guide: `website/docs/developer-guide/model-provider-plugin.md`.

### Dashboard / context-engine / image-gen plugins

Follow the same ABC + orchestrator + per-plugin directory pattern. Reference / example plugins: [`hermes-example-plugins`](https://github.com/NousResearch/hermes-example-plugins) companion repo.

---

## Skills

Two parallel surfaces:

- **`skills/`** — built-in skills shipped and active by default. Organized by category directories.
- **`optional-skills/`** — heavier or niche skills, NOT active by default. Installed via `hermes skills install official/<category>/<skill>`. Categories: `autonomous-ai-agents`, `blockchain`, `communication`, `creative`, `devops`, `email`, `health`, `mcp`, `migration`, `mlops`, `productivity`, `research`, `security`, `web-development`.

### SKILL.md frontmatter

Standard fields: `name`, `description` (≤60 chars, one sentence), `version`, `author`, `license`, `platforms`, `metadata.hermes.tags`, `metadata.hermes.category`, `metadata.hermes.related_skills`, `metadata.hermes.config`.

See CONTRIBUTING.md for the full hardline authoring standards (8 rules), section order requirements, and the external PR salvage checklist.

---

## Toolsets

All toolsets defined in `toolsets.py` as a single `TOOLSETS` dict. Each platform's adapter picks a base toolset; `_HERMES_CORE_TOOLS` is the default bundle most platforms inherit from. Enable/disable per platform via `hermes tools` or `tools.<platform>.enabled`/`disabled` in `config.yaml`.

Current toolset keys: `browser`, `clarify`, `code_execution`, `cronjob`, `debugging`, `delegation`, `discord`, `discord_admin`, `feishu_doc`, `feishu_drive`, `file`, `homeassistant`, `image_gen`, `kanban`, `memory`, `messaging`, `moa`, `rl`, `safe`, `search`, `session_search`, `skills`, `spotify`, `terminal`, `todo`, `tts`, `video`, `vision`, `web`, `yuanbao`.

---

## Delegation (`delegate_task`)

`tools/delegate_tool.py` spawns a subagent with isolated context + terminal session. With `background=true`, returns a delegation id immediately; result re-enters conversation via async queue.

- `role="leaf"` (default) — focused worker; cannot call `delegate_task`, `clarify`, `memory`, `send_message`, `execute_code`.
- `role="orchestrator"` — retains `delegate_task`; gated by `delegation.orchestrator_enabled` (default true), bounded by `delegation.max_spawn_depth` (default 2).

Key config knobs under `delegation:` in `config.yaml`: `max_concurrent_children`, `max_spawn_depth`, `child_timeout_seconds`, `orchestrator_enabled`, `subagent_auto_approve`, `inherit_mcp_toolsets`, `max_iterations`.

**Durability:** background `delegate_task` is process-local. For work that must survive process restart, use `cronjob` or `terminal(background=True, notify_on_complete=True)`.

---

## Curator (skill lifecycle)

`agent/curator.py` + `agent/curator_backup.py`. Tracks usage on agent-created skills and auto-archives stale ones. Archives go to `~/.hermes/skills/.archive/` and are restorable. CLI: `hermes curator <status|run|pause|resume|pin|unpin|archive|restore|prune|backup|rollback>`.

Invariants: only touches `created_by: "agent"` skills; never deletes; pinned skills exempt from all auto-transitions and LLM review pass. Docs: `website/docs/user-guide/features/curator.md`.

---

## Cron (scheduled jobs)

`cron/jobs.py` (job store) + `cron/scheduler.py` (tick loop). CLI: `hermes cron <list|add|edit|pause|resume|run|remove>` or `/cron`.

Schedule formats: duration (`"30m"`, `"2h"`), "every" phrase (`"every monday 9am"`), 5-field cron (`"0 9 * * *"`), ISO timestamp (one-shot). Per-job fields: `skills`, `model`/`provider` overrides, `script` (pre-run data collection), `context_from` (chain prior job output), `workdir`. Hard interrupt at 3 minutes; cron sessions pass `skip_memory=True`.

---

## Kanban (multi-agent work queue)

Durable SQLite-backed board. CLI: `hermes kanban <init|create|list|show|assign|link|complete|block|unblock|...>`. Worker toolset: `tools/kanban_tools.py`. Dispatcher: long-lived loop (default every 60s), runs inside the gateway by default (`kanban.dispatch_in_gateway: true`). Plugin assets: `plugins/kanban/`.

Isolation: Board is the hard boundary — workers are spawned with `HERMES_KANBAN_BOARD` pinned. After `kanban.failure_limit` (default 2) consecutive failures on the same task, the dispatcher auto-blocks it. Docs: `website/docs/user-guide/features/kanban.md`.

---

## Important Policies

### Prompt Caching Must Not Break

**Do NOT implement changes that would:** alter past context mid-conversation, change toolsets mid-conversation, or reload memories/rebuild system prompts mid-conversation. Cache-breaking forces dramatically higher costs. Slash commands that mutate system-prompt state must default to deferred invalidation (change takes effect next session), with opt-in `--now` flag for immediate invalidation.

### Background Process Notifications (Gateway)

Control with `display.background_process_notifications` in config.yaml (or `HERMES_BACKGROUND_NOTIFICATIONS` env var): `all` (default), `result`, `error`, `off`.

---

## Profiles: Multi-Instance Support

Each profile has its own `HERMES_HOME` directory. `_apply_profile_override()` in `hermes_cli/main.py` sets `HERMES_HOME` before any module imports. All `get_hermes_home()` references automatically scope to the active profile.

**Critical rule:** Use `get_hermes_home()` (from `hermes_constants`) for all HERMES_HOME paths. Use `display_hermes_home()` for user-facing messages. **NEVER hardcode `~/.hermes` or `Path.home() / ".hermes"` in code that reads/writes state** — this breaks profiles and was the source of 5 bugs fixed in PR #3575.

Profile operations (listing, creating) are HOME-anchored (`Path.home() / ".hermes" / "profiles"`), NOT HERMES_HOME-anchored — this is intentional so `hermes -p coder profile list` can see all profiles regardless of which one is active.

See CONTRIBUTING.md for full profile-safe coding rules and test fixture patterns.

---

## Known Pitfalls

### DO NOT hardcode `~/.hermes` paths
Use `get_hermes_home()` from `hermes_constants` for code paths. Use `display_hermes_home()` for user-facing messages. Hardcoding `~/.hermes` breaks profiles. Source of 5 bugs fixed in PR #3575.

### DO NOT introduce new `simple_term_menu` usage
Existing call sites in `hermes_cli/main.py` remain for legacy fallback only. New interactive menus must use `hermes_cli/curses_ui.py` — see `hermes_cli/tools_config.py` for the canonical pattern. `simple_term_menu` has ghost-duplication rendering bugs in tmux/iTerm2.

### DO NOT use `\033[K` (ANSI erase-to-EOL) in spinner/display code
Leaks as literal `?[K` text under `prompt_toolkit`'s `patch_stdout`. Use space-padding: `f"\r{line}{' ' * pad}"`.

### `_last_resolved_tool_names` is a process-global in `model_tools.py`
`_run_single_child()` in `delegate_tool.py` saves and restores this global around subagent execution. New code that reads this global may see temporarily stale values during child agent runs.

### DO NOT hardcode cross-tool references in schema descriptions
Tool schema descriptions must not mention tools from other toolsets by name (e.g. `browser_navigate` saying "prefer web_search"). Those tools may be unavailable. If needed, add dynamically in `get_tool_definitions()` in `model_tools.py` — see the `browser_navigate` / `execute_code` post-processing blocks for the pattern.

### The gateway has TWO message guards — both must bypass approval/control commands
When an agent is running, messages pass through: (1) **base adapter** (`gateway/platforms/base.py`) queues in `_pending_messages` when `session_key in self._active_sessions`, and (2) **gateway runner** (`gateway/run.py`) intercepts `/stop`, `/new`, `/queue`, `/status`, `/approve`, `/deny`. Any new command that must reach the runner while the agent is blocked MUST bypass BOTH guards and dispatch inline, not via `_process_message_background()`.

### Squash merges from stale branches silently revert recent fixes
Before squash-merging a PR, ensure the branch is up to date with `main`. Verify with `git diff HEAD~1..HEAD` after merging — unexpected deletions are a red flag.

### Don't wire in dead code without E2E validation
Before wiring an unused module into a live code path, E2E test the real resolution chain with actual imports (not mocks) against a temp `HERMES_HOME`.

### Tests must not write to `~/.hermes/`
The `_isolate_hermes_home` autouse fixture in `tests/conftest.py` redirects `HERMES_HOME` to a temp dir. Never hardcode `~/.hermes/` paths in tests. Profile tests: also mock `Path.home()` — see `tests/hermes_cli/test_profiles.py` for the fixture pattern.

---

## Testing

**ALWAYS use `scripts/run_tests.sh`** — do not call `pytest` directly. The script enforces hermetic environment parity with CI (unset credential vars, TZ=UTC, LANG=C.UTF-8, `-n auto` xdist workers, subprocess-isolation plugin).

```bash
scripts/run_tests.sh                                  # full suite, CI-parity
scripts/run_tests.sh tests/gateway/                   # one directory
scripts/run_tests.sh tests/agent/test_foo.py::test_x  # one test
scripts/run_tests.sh -v --tb=long                     # pass-through pytest flags
scripts/run_tests.sh --no-isolate tests/foo/          # disable subprocess isolation (faster, for debugging)
```

Every test runs in a fresh subprocess (via `tests/_isolate_plugin.py`, `multiprocessing.get_context("spawn")`), preventing module-level state leakage between tests. `isolate_timeout` in `pyproject.toml` caps each test at 30s.

See CONTRIBUTING.md for: why the wrapper exists (five CI drift sources), subprocess isolation implementation details, and the "don't write change-detector tests" guideline.
