# Hermes Agent — Contributor Guide

Detailed guidance for humans (and AI assistants) contributing to the hermes-agent codebase: PR policies, dependency rules, authoring standards, and deep-dive architecture.

**This file is NOT loaded by Hermes at runtime.** It is a companion to `AGENTS.md`, which contains the runtime-essential subset. Load this file when you are: reviewing PRs, writing new skills/plugins/skins, debugging CI, or extending the TUI/desktop app.

---

## Contribution Rubric — What We Want / What We Don't

This is the project's intent layer. Use it two ways:

1. **For humans and for your own work** — what gets merged and what gets rejected, so a contribution aims at the target.
2. **For automated review (the triage sweeper)** — guidance on when a PR is safe to close on the three allowed reasons (`implemented_on_main`, `cannot_reproduce`, `incoherent`) and, just as important, **when NOT to close** one. Taste-based "we don't want this / out of scope" closes are NOT an automated decision — those stay with a human maintainer.

Read the balance right: Hermes ships a **lot** — most merges are bug fixes to real reported behavior, and the product surface expands aggressively and on purpose. The restraint below is aimed squarely at the **core agent + the model tool schema**, the one place where every addition is paid for on every API call.

### What we want

- **Fix real bugs, well.** A good fix reproduces the symptom on current `main`, points to the exact line where it manifests, and fixes the whole bug class — sibling call paths included — not just the one site the reporter hit.
- **Expand reach at the edges.** New platform adapters, channels, providers, models, and desktop/TUI/dashboard features are welcome and land routinely, including large ones. Breadth in the product is a goal, not a footprint concern — as long as it integrates with the existing setup/config UX (`hermes tools`, `hermes setup`, auto-install) rather than bolting on a raw env var.
- **Refactor god-files into clean modules.** Extracting a multi-thousand-line cluster out of `cli.py` / `run_agent.py` / `gateway/run.py` into a focused mixin or module is wanted work, even when the diff is huge and mechanical. The "every line traces to the request" test applies to *feature* PRs; a declared refactor's request IS the extraction.
- **Keep the core narrow.** New *model tools* are the expensive exception — every tool ships on every API call. Prefer, in order: extend existing code → CLI command + skill → service-gated tool (`check_fn`) → plugin → MCP server in the catalog → new core tool (last resort).
- **Extend, don't duplicate.** Before adding a module/manager/hook, check whether existing infrastructure already covers the use case.
- **Behavior contracts over snapshots.** Tests should assert how two pieces of data must relate (invariants), not freeze a current value.
- **E2E validation, not just green unit mocks.** For anything touching resolution chains, config propagation, security boundaries, remote backends, or file/network I/O, exercise the real path with real imports against a temp `HERMES_HOME`. Mocks hide integration bugs.
- **Cache-, alternation-, and invariant-safe.** Preserve prompt caching, strict message role alternation, and a byte-stable system prompt.
- **Contributor credit preserved.** Salvage external work by cherry-picking so authorship survives in git history.

### What we don't want (rejected even when well-built)

- **Speculative infrastructure.** Hooks, callbacks, or extension points with no concrete consumer. A hook is NOT speculative if a contributor has a real, stated use case — even if the consumer ships separately.
- **New `HERMES_*` env vars for non-secret config.** `.env` is for secrets only. All behavioral settings go in `config.yaml`.
- **A new core tool when terminal + file already do the job, or when a skill would.**
- **Lazy-reading escape hatches on instructional tools.** No `offset`/`limit` pagination on tools that load content the agent must read fully.
- **"Fixes" that destroy the feature they secure.** A mitigation that kills the feature's purpose is the wrong mitigation.
- **Outbound telemetry / usage attribution without opt-in gating.** No new analytics until a generic user-facing opt-in exists.
- **Change-detector tests, cache-breaking mid-conversation, dead code wired in without E2E proof, and plugins that touch core files.**

### Before you call it a bug — verify the premise

- **"Intentional design, not a gap."** A limitation that looks like an oversight is often deliberate. Read the original commit's intent (`git log -p -S "<symbol>"`) before assuming something is unfinished.
- **"The premise doesn't hold against how X actually works."** Trace the real code/runtime before accepting the rationale. If you can't point to the exact line where the bug manifests AND show the fix changes that line's behavior, you haven't verified the premise.
- **"This fix was wrong — the absence/omission was deliberate."** Adding the obvious-looking missing piece can break things the omission was protecting (e.g., restoring "missing" `__init__.py` files made a test tree importable as a dotted package that shadowed the real plugin).
- **"Overreached / resurrected an approach we'd moved past."** Keep the change to the narrow piece that was agreed; offer the rest as a focused follow-up.

The throughline: **verify the claim AND the intent against the codebase before writing or merging a fix.**

### The Footprint Ladder (new capability decision)

Each rung adds more permanent surface than the one above. Choose the highest (least-footprint) rung that correctly solves the problem:

1. **Extend existing code** — zero new surface.
2. **CLI command + skill** — manages config/state/infra expressible as shell commands. Zero model-tool footprint.
3. **Service-gated tool (`check_fn`)** — needs structured params/returns AND only appears when a prerequisite is configured. Zero footprint otherwise.
4. **Plugin** — third-party/niche/user-specific capability that doesn't ship in core.
5. **MCP server (in the catalog)** — if the capability genuinely needs to be a tool but isn't core-fundamental, prefer an MCP server over growing core.
6. **New core tool** — only when fundamental, broadly useful to nearly every user, and unreachable via terminal + file or an MCP server.

When 3+ open PRs try to integrate the same *category* of thing (memory backends, providers, notifiers), don't merge them one at a time — design an ABC + orchestrator, wrap the existing built-in as the first provider, and turn the competing PRs into plugins against that interface.

---

## Dependency Pinning Policy

All dependencies must have upper bounds to limit supply-chain attack surface. This policy was established after the litellm compromise (PR #2796, #2810) and reinforced after the Mini Shai-Hulud worm campaign (May 2026).

| Source type | Treatment | Example |
|---|---|---|
| PyPI package | `>=floor,<next_major` | `"httpx>=0.28.1,<1"` |
| Git URL | Commit SHA | `git+https://...@<40-char-sha>` |
| GitHub Actions | Commit SHA + comment | `uses: actions/checkout@<sha>  # v4` |
| CI-only pip | `==exact` | `pyyaml==6.0.2` |

**When adding a new dependency to `pyproject.toml`:**
1. Pin to `>=current_version,<next_major` for post-1.0 (e.g. `>=1.5.0,<2`).
2. For pre-1.0 packages, use `<0.(current_minor + 2)` (e.g. `>=0.29,<0.32`).
3. Never commit a bare `>=X.Y.Z` without a ceiling — CI and reviewers will reject it.
4. Run `uv lock` to regenerate `uv.lock` with hashes.

Reference: #2810 (bounds pass), #9801 (SHA pinning + audit CI).

---

## Skill Authoring Standards (HARDLINE)

Every new or modernized skill — bundled, optional, or contributed — must meet these standards before merge. Reviewers reject PRs that violate them.

1. **`description` ≤ 60 characters, one sentence, ends with a period.** Long descriptions bloat skill listings. State the capability, not the implementation. No marketing words. Don't repeat the skill name. Verify:
   ```python
   import re, pathlib
   m = re.search(r'^description: (.*)$', pathlib.Path('skills/<cat>/<name>/SKILL.md').read_text(), re.MULTILINE)
   assert len(m.group(1)) <= 60, len(m.group(1))
   ```

2. **Tools referenced in SKILL.md prose must be native Hermes tools or MCP servers the skill explicitly expects.** Point at the proper tool in backticks: `` `terminal` ``, `` `web_extract` ``, `` `read_file` ``, `` `patch` ``, `` `search_files` ``, `` `vision_analyze` ``, `` `browser_navigate` ``, `` `delegate_task` ``. Do NOT name shell utilities the agent already has wrapped (`grep` → `search_files`, `cat`/`head`/`tail` → `read_file`, `sed`/`awk` → `patch`, `find`/`ls` → `search_files target='files'`).

3. **`platforms:` gating audited against actual script imports.** Skills that use POSIX-only primitives must declare their supported platforms. Default posture: try to fix it cross-platform first.

4. **`author` credits the human contributor first.** If the contributor used Hermes to draft the skill, replace "Hermes Agent" as commit author with their actual name.

5. **SKILL.md body uses the modern section order.** `# <Skill> Skill` title, 2-3 sentence intro, `## When to Use`, `## Prerequisites`, `## How to Run`, `## Quick Reference`, `## Procedure`, `## Pitfalls`, `## Verification`. Target ~200 lines for complex, ~100 for simple. Cut redundant intro fluff and marketing prose.

6. **Scripts go in `scripts/`, references in `references/`, templates in `templates/`.** Ship helper scripts rather than having the model inline-write non-trivial logic every call.

7. **Tests live at `tests/skills/test_<skill>_skill.py`** — stdlib + pytest + `unittest.mock` only. No live network calls.

8. **`.env.example` additions are isolated to a clearly delimited block.** Don't touch the surrounding file.

The full salvage / modernization checklist for external skill PRs lives in the `hermes-agent-dev` skill at `references/new-skill-pr-salvage.md`.

---

## Skin / Theme Authoring

### Adding a built-in skin

Add to `_BUILTIN_SKINS` dict in `hermes_cli/skin_engine.py`:

```python
"mytheme": {
    "name": "mytheme",
    "description": "Short description",
    "colors": { ... },
    "spinner": { ... },
    "branding": { ... },
    "tool_prefix": "┊",
},
```

### User skins (YAML format)

Users create `~/.hermes/skins/<name>.yaml`:

```yaml
name: cyberpunk
description: Neon-soaked terminal theme

colors:
  banner_border: "#FF00FF"
  banner_title: "#00FFFF"
  banner_accent: "#FF1493"

spinner:
  thinking_verbs: ["jacking in", "decrypting", "uploading"]
  wings:
    - ["⟨⚡", "⚡⟩"]

branding:
  agent_name: "Cyber Agent"
  response_label: " ⚡ Cyber "

tool_prefix: "▏"
```

### What skins customize

| Element | Skin Key | Used By |
|---------|----------|---------|
| Banner panel border | `colors.banner_border` | `banner.py` |
| Banner panel title | `colors.banner_title` | `banner.py` |
| Response box border | `colors.response_border` | `cli.py` |
| Spinner faces (waiting) | `spinner.waiting_faces` | `display.py` |
| Spinner faces (thinking) | `spinner.thinking_faces` | `display.py` |
| Spinner verbs | `spinner.thinking_verbs` | `display.py` |
| Spinner wings | `spinner.wings` | `display.py` |
| Tool output prefix | `tool_prefix` | `display.py` |
| Per-tool emojis | `tool_emojis` | `display.py` |
| Agent name | `branding.agent_name` | `banner.py`, `cli.py` |
| Welcome message | `branding.welcome` | `cli.py` |
| Response box label | `branding.response_label` | `cli.py` |
| Prompt symbol | `branding.prompt_symbol` | `cli.py` |

---

## Profile-Safe Coding Rules

All code that reads or writes HERMES_HOME state must follow these rules:

1. **Use `get_hermes_home()` for all HERMES_HOME paths.**
   ```python
   # GOOD
   from hermes_constants import get_hermes_home
   config_path = get_hermes_home() / "config.yaml"

   # BAD — breaks profiles
   config_path = Path.home() / ".hermes" / "config.yaml"
   ```

2. **Use `display_hermes_home()` for user-facing messages.**
   ```python
   from hermes_constants import display_hermes_home
   print(f"Config saved to {display_hermes_home()}/config.yaml")
   ```

3. **Module-level constants are fine** — they cache `get_hermes_home()` at import time, after `_apply_profile_override()` sets the env var.

4. **Tests that mock `Path.home()` must also set `HERMES_HOME`:**
   ```python
   with patch.object(Path, "home", return_value=tmp_path), \
        patch.dict(os.environ, {"HERMES_HOME": str(tmp_path / ".hermes")}):
       ...
   ```

5. **Gateway platform adapters should use token locks** — call `acquire_scoped_lock()` from `gateway.status` in `connect()`/`start()` and `release_scoped_lock()` in `disconnect()`/`stop()`. See `plugins/platforms/irc/adapter.py` for the canonical pattern.

6. **Profile operations are HOME-anchored, not HERMES_HOME-anchored** — `_get_profiles_root()` returns `Path.home() / ".hermes" / "profiles"`, NOT `get_hermes_home() / "profiles"`. This is intentional.

### Profile test fixture

```python
@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home
```

---

## TUI Architecture — Detailed Reference

### Process Model

```
hermes --tui
  └─ Node (Ink)  ──stdio JSON-RPC──  Python (tui_gateway)
       │                                  └─ AIAgent + tools + sessions
       └─ renders transcript, composer, prompts, activity
```

Transport: newline-delimited JSON-RPC over stdio. Requests from Ink, events from Python. See `tui_gateway/server.py` for the full method/event catalog.

### Key Surfaces

| Surface | Ink component | Gateway method |
|---------|---------------|----------------|
| Chat streaming | `app.tsx` + `messageLine.tsx` | `prompt.submit` → `message.delta/complete` |
| Tool activity | `thinking.tsx` | `tool.start/progress/complete` |
| Approvals | `prompts.tsx` | `approval.respond` ← `approval.request` |
| Clarify/sudo/secret | `prompts.tsx`, `maskedPrompt.tsx` | `clarify/sudo/secret.respond` |
| Session picker | `sessionPicker.tsx` | `session.list/resume` |
| Slash commands | Local handler + fallthrough | `slash.exec` → `_SlashWorker`, `command.dispatch` |
| Completions | `useCompletion` hook | `complete.slash`, `complete.path` |
| Theming | `theme.ts` + `branding.tsx` | `gateway.ready` with skin data |

### Slash Command Flow

1. Built-in client commands (`/help`, `/quit`, `/clear`, `/resume`, `/copy`, `/paste`) handled locally in `app.tsx`
2. Everything else → `slash.exec` (persistent `_SlashWorker` subprocess) → `command.dispatch` fallback

### Dev Commands

```bash
cd ui-tui
npm install       # first time
npm run dev       # watch mode
npm start         # production
npm run build     # full build
npm run typecheck # tsc --noEmit
npm run lint      # eslint
npm run fmt       # prettier
npm test          # vitest
```

### Dashboard TUI (`hermes dashboard` → `/chat`)

Browser loads `web/src/pages/ChatPage.tsx` with xterm.js WebGL renderer. `/api/pty?token=…` upgrades to WebSocket. Server spawns `hermes --tui` through `ptyprocess`. Resize via `\x1b[RESIZE:<cols>;<rows>]` intercepted on the server. **Do not re-implement the primary chat experience in React** — extend Ink instead.

---

## Electron Desktop App — Detailed Reference (`apps/desktop/`)

Electron + React + nanostore + `@assistant-ui/react` talking to `tui_gateway` over JSON-RPC (`requestGateway(method, params)`). Does NOT embed `hermes --tui` — it has its own composer, transcript, and slash-command pipeline.

### Slash Command Pipeline

- **Backend provides everything.** `tui_gateway/server.py` `commands.catalog` and `complete.slash` include built-in commands, user `quick_commands`, AND skill-derived commands (`scan_skill_commands()` / `get_skill_commands()`). The desktop app does not need a new RPC to see skills.
- **`apps/desktop/src/lib/desktop-slash-commands.ts`** is the load-bearing curation file. It holds `DESKTOP_COMMANDS` (the ~19 built-ins shown in the palette) plus block-lists for terminal-only / messaging-only / picker-owned / settings-owned / advanced commands.
  - `isDesktopSlashCommand(name)` — gates **execution**.
  - `isDesktopSlashSuggestion(name)` — gates **discovery/completion**. Used by BOTH completion paths.
  - `isDesktopSlashExtensionCommand(name)` — true when the command is NOT a known Hermes built-in (skill or quick command). Both suggestion and catalog-filter paths allow extensions through.
- **Dispatch** in `app/session/hooks/use-prompt-actions.ts` (`runSlash`): built-ins handled locally; everything else → `slash.exec`, fallback to `command.dispatch`.

**Rule:** the desktop slash palette's curation is about hiding noise (terminal-only / messaging-only built-ins), NOT about hiding user-activated extensions. Skill commands and `quick_commands` belong in completions. If you tighten `desktop-slash-commands.ts`, keep `isDesktopSlashExtensionCommand` flowing into both paths. Tests: `apps/desktop/src/lib/desktop-slash-commands.test.ts`.

Route desktop bugs to the `hermes-desktop-app-work` skill, not `hermes-dashboard-work`.

---

## Testing — Advanced Topics

### Why the test wrapper exists

Five real sources of local-vs-CI drift the script closes:

| | Without wrapper | With wrapper |
|---|---|---|
| Provider API keys | Whatever is in your env | All `*_API_KEY`/`*_TOKEN`/etc. unset |
| HOME / `~/.hermes/` | Your real config+auth.json | Temp dir per test |
| Timezone | Local TZ (PDT etc.) | UTC |
| Locale | Whatever is set | C.UTF-8 |
| xdist workers | `-n auto` = all cores | `-n auto` (safe — subprocess isolation prevents cross-worker flakes) |

### Subprocess-per-test isolation

Every test runs in a freshly-spawned Python subprocess via `tests/_isolate_plugin.py`. This means module-level dicts/sets and ContextVars from one test cannot leak into the next. Implementation:

- Uses `multiprocessing.get_context("spawn")` — works on Linux, macOS, and Windows.
- Per-test overhead: ~0.5–1.0s (Python startup + pytest collection). xdist parallelism amortizes this.
- `isolate_timeout` in `pyproject.toml` caps each test at 30s. Hangs are killed and surfaced as a failure report.
- Pass `--no-isolate` to disable isolation for interactive debugging or state-leakage verification.
- Disables itself in child processes via `HERMES_ISOLATE_CHILD=1` sentinel envvar.

### Don't write change-detector tests

A test is a **change-detector** if it fails whenever data that is **expected to change** gets updated.

**Do not write:**
```python
assert "gemini-2.5-pro" in _PROVIDER_MODELS["gemini"]  # catalog snapshot
assert DEFAULT_CONFIG["_config_version"] == 21          # config version literal
assert len(_PROVIDER_MODELS["huggingface"]) == 8        # enumeration count
```

**Do write:**
```python
assert "gemini" in _PROVIDER_MODELS                     # does the catalog plumbing work?
assert len(_PROVIDER_MODELS["gemini"]) >= 1
assert raw["_config_version"] == DEFAULT_CONFIG["_config_version"]  # migration bumps version
assert not (set(moonshot_models) & coding_plan_only_models)         # invariant: no leakage
for m in _PROVIDER_MODELS["huggingface"]:                           # invariant: all have context lengths
    assert m.lower() in DEFAULT_CONTEXT_LENGTHS_LOWER
```

The rule: if the test reads like a snapshot of current data, delete it. If it reads like a contract about how two pieces of data must relate, keep it.
