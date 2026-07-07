# Suggested Commands

All commands run from repo root (`/Users/matthewgold/.hermes/hermes-agent/`).
Use `uv run` to stay in the managed venv without activating it first.

## Development
```bash
uv sync --extra dev          # Install all dev dependencies
uv run hermes                # Run the CLI (via console_scripts entry point)
uv run hermes chat           # Start interactive chat
uv run hermes --version      # Print version
```

## Testing
```bash
uv run pytest tests/                        # All non-integration tests
uv run pytest tests/ -m "not integration"   # Explicitly skip integration tests
uv run pytest tests/ -m integration         # Integration tests only (need API keys)
uv run pytest tests/path/to/test_foo.py -x  # Single file, stop on first failure
```

Integration tests are marked `@pytest.mark.integration` and require external API keys. Normal CI only runs `not integration`.

## Linting & Formatting
```bash
uv run ruff check .          # Lint
uv run ruff check . --fix    # Lint + auto-fix
uv run ruff format .         # Format
uv run ruff format --check . # Format check only (CI mode)
```

## Type Checking
```bash
uv run ty check              # Type check (NOT mypy — this project uses ty)
```

## Building TUI (TypeScript)
```bash
cd ui-tui && npm install && npm run build
```
