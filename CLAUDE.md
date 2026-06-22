# hermes-agent — Claude Code Instructions

## Code Intelligence Tools (use in this order)

1. **codegraph** (primary) — pre-built structural graph of all symbols + call edges. Use `codegraph_explore` first for any code question, architecture overview, or before editing. One call returns verbatim source + callers. The `.codegraph/` symlink at repo root points to the live index at `~/.omo/codegraph/projects/.hermes-e4f99ecb07fadec4/`.

2. **serena** — LSP-backed symbol navigation for this project (Python, activated). Use for: rename, find-references, go-to-definition, get-symbols-overview on a file. Best when you need to understand the shape of a specific file or perform a precise symbol-level operation.

3. **wozcode Search** — file discovery and lexical content search. Use when you know what text to look for or need to find files matching a pattern.

4. **ck semantic search** — indexed and operational (`jina-code` model, 1,565 files / 40,530 chunks, `hermes-agent/.ck/`). Use for meaning-based queries when codegraph doesn't have the right symbol names.

   Preferred call pattern for agents:
   - `hybrid_search(query, page_size=20, snippet_length=400)` — best default (semantic + BM25)
   - `semantic_search(query, threshold=0.55, page_size=15)` — pure meaning, raise threshold for precision
   - `regex_search(pattern, page_size=30)` — exact pattern, use wozcode Search instead for most cases
   - Add `include_snippet=false` when you only need file paths
   - The index lives at `hermes-agent/.ck/` (model: `jina-code`, 768 dims, 1024-tok chunks). Run `ck --status .` from `hermes-agent/` to check.
   - **Critical `.ckignore` rules** (must be present or indexing hangs/loops): `.ck/` (never index the index itself) and `**/node_modules/` (catches nested ones under `web/`, `plugins/`, etc.)
   - **Safety: preventing runaway indexing** — ck v0.7.11+ can hang if `.ck/` is not excluded: (1) verify `.ckignore` has `.ck/` and `**/node_modules/`; (2) monitor: `watch -n 1 'ps aux | grep ck | grep -v grep'` + `ck --switch-model <name>`; (3) kill if runaway: `pkill -9 -f "ck-search"` if CPU >80% or RSS >5GB for >5 min (normal <10 min); (4) `.ckignore` fix is the real prevention — without it, ck re-indexes its own binary infinitely
   - **Safety: preventing runaway indexing** — ck v0.7.11+ can hang if `.ck/` not excluded: (1) verify `.ckignore` has `.ck/` and `**/node_modules/`; (2) monitor: `watch -n 1 'ps aux | grep ck | grep -v grep'` + `ck --switch-model <name>`; (3) kill if runaway: `pkill -9 -f "ck-search"` if CPU >80% or RSS >5GB for >5 min (normal <10 min); (4) `.ckignore` fix is the real prevention — without it, ck re-indexes its own binary infinitely
   - **Safety: preventing runaway indexing** — ck v0.7.11+ can hang if `.ck/` is not excluded. Before reindexing: (1) verify `.ckignore` contains `.ck/` and `**/node_modules/`; (2) monitor: `watch -n 1 'ps aux | grep ck | grep -v grep'` in one terminal, `ck --switch-model <name>` in another; (3) kill if runaway: `pkill -9 -f "ck-search"` if CPU >80% or RSS >5GB for >5 min (normal reindex <10 min); (4) the `.ckignore` fix is the real prevention—without it, ck re-indexes its own binary index infinitely.

**Embedding models** — set at index time; `ck --switch-model <name>` triggers a full reindex:

| Model | Dims | Context | Best for |
|-------|------|---------|----------|
| `bge-small` | 384 | 512 tok | Default — fastest, lowest RAM; general mixed codebases |
| `nomic-v1.5` | 768 | 8192 tok | Long-context files; prose-heavy docs mixed with code |
| `jina-code` | 768 | 1024 tok | **Code-specialized** — best semantic understanding of code constructs; **current index** |
| `mxbai-xsmall` | 384 | 512 tok | Smallest footprint; similar quality to bge-small |

**Reranking** — applied at query time, no reindex needed (`--rerank --rerank-model <name>`):
`jina` (default, multilingual), `bge`, `mxbai` — all general-purpose cross-encoders, none code-specialized. Omit for MCP use (latency cost outweighs benefit at tool-call granularity).

## Project Quick Reference

- **Entry point**: `hermes_cli/main.py` → `main()`
- **Python**: 3.11–3.13 (NOT 3.14 — Rust wheels missing)
- **Package manager**: uv (`uv sync --extra dev` to install)
- **Linter**: ruff | **Type checker**: ty (NOT mypy) | **Tests**: pytest
- **Run tests**: `uv run pytest tests/ -m "not integration"`
- **Lint**: `uv run ruff check .` | **Format**: `uv run ruff format .`

## Key Invariants

- All deps in `pyproject.toml` are exact-pinned (`==X.Y.Z`) — never add ranges.
- Lazy imports inside `cmd_*` functions — don't add top-level feature imports to `main.py`.
- Runtime state is in `~/.hermes/`, not the repo. Config: `~/.hermes/config.yaml`.

See serena memories for full detail: `serena memories check` from repo root.
