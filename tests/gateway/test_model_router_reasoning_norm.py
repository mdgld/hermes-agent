"""Tests for _normalize_reasoning_for_provider (Todo 2 — router-enhancements)."""
import importlib.util
import uuid
from pathlib import Path

PLUGIN_PATH = Path("/Users/matthewgold/.hermes/plugins/model-router/__init__.py")


def _load_plugin(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    mod_name = f"test_mr_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(mod_name, PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    mod._manager_ref = None
    return mod, hermes_home


def test_max_maps_to_xhigh_for_openrouter(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    assert mod._normalize_reasoning_for_provider("max", "openrouter") == "xhigh"


def test_xhigh_passes_through_for_openrouter(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    assert mod._normalize_reasoning_for_provider("xhigh", "openrouter") == "xhigh"


def test_max_is_noop_for_bedrock(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    assert mod._normalize_reasoning_for_provider("max", "bedrock") == "max"


def test_xhigh_is_noop_for_bedrock(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    assert mod._normalize_reasoning_for_provider("xhigh", "bedrock") == "xhigh"


def test_enabled_maps_to_medium_for_openai_codex(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    assert mod._normalize_reasoning_for_provider("enabled", "openai-codex") == "medium"


def test_high_passes_through_for_nous(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    assert mod._normalize_reasoning_for_provider("high", "nous") == "high"


def test_none_effort_returns_none(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    assert mod._normalize_reasoning_for_provider(None, "openrouter") is None


def test_empty_provider_returns_effort_unchanged(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    assert mod._normalize_reasoning_for_provider("max", "") == "max"


def test_unknown_provider_uses_default_map(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    assert mod._normalize_reasoning_for_provider("max", "some-unknown-llm") == "xhigh"


def test_max_maps_to_xhigh_for_openai(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    assert mod._normalize_reasoning_for_provider("max", "openai") == "xhigh"
