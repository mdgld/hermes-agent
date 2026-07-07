# Task Completion Checklist

Run these before considering a coding task done:

```bash
# 1. Lint (must pass clean)
uv run ruff check .

# 2. Format check
uv run ruff format --check .

# 3. Type check
uv run ty check

# 4. Unit tests (non-integration)
uv run pytest tests/ -m "not integration" -x
```

If you added a new dependency, also run:
```bash
uv lock   # regenerate uv.lock after pyproject.toml change
```

If you touched `ui-tui/`:
```bash
cd ui-tui && npm run build
```

**Do not run integration tests** as part of routine task completion — they require live API keys and are slow.
