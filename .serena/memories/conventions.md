# Code Conventions

## Python style
- Ruff enforced; see `[tool.ruff.lint]` in pyproject.toml for active rules (intentionally narrow set)
- Tests under `tests/` may use `PLW1514` (open without encoding) — explicitly ignored per-file
- Type checker: `ty` (not mypy). Type annotations expected on public functions.

## Dependency management
- **Never add ranges** to `pyproject.toml` dependencies. All direct deps must be exact-pinned (`==X.Y.Z`). When bumping, update `uv.lock` with `uv lock`.
- Provider-specific packages go in extras, not `dependencies`, to limit blast radius of supply-chain incidents.

## CLI pattern
- Subcommand handlers are `cmd_<name>(args)` functions in `hermes_cli/main.py` or separate modules imported lazily.
- Lazy imports inside `cmd_*` functions — do NOT add top-level imports for feature modules.
- Parser builders are named `build_<name>_parser(subparsers, cmd_<name>=cmd_<name>)` and live in `hermes_cli/subcommands/<name>.py`.

## Testing
- Mark slow or API-dependent tests `@pytest.mark.integration`.
- Async tests use `pytest-asyncio`.
- Fixtures live in `tests/fixtures/` (including example plugins).

## Hermes home
- Runtime state stored in `~/.hermes/` (not the repo). `hermes_constants.get_hermes_home()` returns the path.
- Config: `~/.hermes/config.yaml` (ruamel.yaml, not standard yaml).
