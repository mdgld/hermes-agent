# Handoff: MoA degradation diagnosis + fallback-chain feature

Session paused after Part A item 3 (langfuse root-trace fix) plus item 4 (trace-leak
fix), to conserve the user's remaining usage. Codex: please continue from "Remaining
work" below. Full plan (approved by user): 
`/Users/matthewgold/.claude/.omc-launch/plans/please-evaluate-the-hermes-crispy-hamming.md`

## Diagnosis recap (already delivered to user, no action needed)

Two independent adversarial reviews (Claude + a `fable`-model reviewer) confirmed the
uncommitted local diff does NOT change model selection, and the user confirmed their
`opus-4-8-moa` preset's sonnet-5 aggregator is intentional — so the reported "severely
degraded" MoA performance is most likely an outside/upstream provider factor, not this
codebase. The actionable work is: (A) fix 6 real bugs the fable review found in the
diff, (B) add fallback chains to MoA (the user's explicit ask), since MoA currently has
zero retry/fallback wiring unlike the primary single-model path.

## Done this session (Part A, items 1-4 of 6)

1. **A1** `agent/agent_runtime_helpers.py`: the mid-session switch-to-MoA branch was
   missing `agent=agent` / `reference_callback=` on `MoAClient(...)` construction
   (present in `agent/agent_init.py` but not mirrored here) — fixed, added the same
   `_moa_reference_relay` closure.
2. **A2** Added `resolve_default_moa_preset_name()` to `hermes_cli/moa_config.py` and
   replaced hardcoded literal `"default"` preset-name fallbacks in
   `agent/agent_init.py`, `agent/agent_runtime_helpers.py`, and
   `hermes_cli/model_switch.py` with it — avoids `KeyError("default")` when a user's
   only/default preset isn't literally named `"default"` (this user's is
   `opus-4-8-moa`).
3. **A3** `agent/moa_loop.py` + `plugins/observability/langfuse/__init__.py`: MoA
   reference/aggregator sub-calls can race the turn's own top-level `pre_api_request`
   and end up being the one that creates the shared Langfuse root trace for that turn
   — previously this stamped the root with the racing sub-call's own
   provider/model instead of the outer agent/session identity. Fixed by threading
   `root_provider`/`root_model` (derived from `agent.provider`/`agent.model`) through
   `_invoke_moa_pre_api_request` → `on_pre_llm_request`, preferred only when creating a
   *new* root trace; non-MoA callers are unaffected (they never pass these kwargs).
4. **A4** Same two files: MoA reference/aggregator failures previously never called the
   `post_api_request` hook at all, so a failed call's Langfuse generation sat open with
   no error info until the whole turn's root trace eventually swept it up (or the
   256-entry LRU eviction backstop closed it with zero context). Added `error: str = ""`
   to `_invoke_moa_post_api_request`, call it from both `_run_reference`'s and
   `aggregate_moa_context`'s `except` branches with `error=str(exc)`, and updated
   `on_post_llm_call` to record the error on the generation's metadata/output when
   present. (Investigated and deliberately did NOT add a new turn-lifecycle hook for
   root-trace-finish — analysis showed the existing `_finish_trace` sweep + accepted
   256-entry LRU eviction already bound this correctly; fable's own review called that
   "Acceptable as bounded.")

All changes verified: `uv run pytest tests/hermes_cli/test_moa_config.py
tests/hermes_cli/test_model_cost_guard.py tests/hermes_cli/test_model_switch_moa_safety.py -q`
→ 32/32 passing, both before and after each change.

## Known pre-existing test-suite issue (NOT caused by this session's edits — verify before blaming new code)

`uv run pytest tests/ -m "not integration" -k "moa or langfuse or fallback"` reports
59 failed / 21 errors, reproducible across repeated runs. Investigated and isolated:
the same individual tests (e.g. `test_streaming.py::TestStreamingFallback::
test_exhausted_transient_stream_error_propagates`,
`test_switch_model_fallback_prune.py::test_switch_within_same_provider_preserves_chain`)
PASS cleanly when run alone or in small groups, and FAIL only inside this large combined
selection alongside dozens of unrelated test files (OAuth, image-fallback, bedrock IAM,
reasoning-extraction — subsystems today's edits never touch). Strong signal of cross-test
global-state pollution (the plugin registry logs re-registering providers multiple times
during the run) rather than a logic regression. `tests/tui_gateway/test_goal_command.py::
test_moa_arg_is_always_one_shot` fails even on a fully pristine `git stash`'d checkout with
zero local changes — it reads this machine's real `~/.hermes/config.yaml`, which has no
preset literally named `"default"` (`default_preset: opus-4-8-moa`), so it's an
environment-specific test bug unrelated to any code, pre-existing before this session.
**Recommend a short separate investigation of pytest test isolation for this suite before
assuming any future failure here is a real regression.**

## Remaining work (see plan file for full detail)

- **A5**: `hermes_cli/web_server.py`'s `set_moa_models` legacy-flat-payload branch
  (~line 4404) destructively rebuilds `moa` config from flat fields only, dropping every
  other named preset. Fix: merge into the existing `presets` map instead.
- **A6**: delete/fix `exact_moa_preset_name`'s stale docstring in `hermes_cli/moa_config.py`
  (dead code, caller removed). In `gateway/slash_commands.py`'s pin refactor, confirm only
  the authoritative session-id namespace needs pinning, and wrap
  `hermes_cli/model_router_pin.py`'s `mgr.discover_and_load()` in `asyncio.to_thread`.
- **B1-B5**: the actual MoA fallback-chain feature (`aggregator_fallbacks` /
  `reference_fallbacks` schema in `moa_config.py`, wired into `_run_reference` and
  `MoAChatCompletions.create()`'s aggregator call in `agent/moa_loop.py` via
  `agent/error_classifier.py`'s `classify_api_error()`/`FailoverReason`, CLI/dashboard
  config UI, and tests). Not started yet — full design is in the plan file's Part B.
- Final verification pass: `ruff check .`, `ruff format --check .`, full test suite,
  manual smoke test per the plan's Verification section.

Task list is tracked live in this session's TaskCreate/TaskUpdate state (tasks #1-12);
Codex should re-derive equivalent tracking or just work through the plan file's Part A
items 5-6 and Part B items 1-5 in order.
