"""Tests for [provider|T{tier}] status bar badge (Todo 1 — router-enhancements)."""
import importlib.util
import uuid
from pathlib import Path
from unittest.mock import MagicMock

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


def _make_cli_stub(mod, session_id: str, tier: int, model: str):
    class _FakeCli:
        def __init__(self):
            self.agent = type("Agent", (), {"session_id": session_id, "model": model})()
            self._router_patched = False

        def _get_status_bar_snapshot(self):
            return {
                "model_name": model,
                "model_short": model.split("/")[-1] if "/" in model else model,
                "duration": "0s",
            }

    cli = _FakeCli()
    with mod._state_lock:
        mod._last_tier[session_id] = tier
    return cli


def test_bedrock_model_shows_aws_provider_badge(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    session_id = "bar-session-1"
    mod._record_runtime_state(
        session_id,
        {"profile_id": "tier_3", "display_name": "T3", "model": "us.anthropic.claude-sonnet-4-6",
         "provider": "bedrock", "base_url": "", "api_mode": "bedrock_converse", "reasoning": "xhigh"},
        3,
    )
    cli = _make_cli_stub(mod, session_id, 3, "us.anthropic.claude-sonnet-4-6")
    mod._patch_status_bar(cli)
    snap = cli._get_status_bar_snapshot()
    assert "[aws|T3]" in snap["model_short"], f"Expected [aws|T3] in {snap['model_short']!r}"
    assert "claude-sonnet-4-6" in snap["model_short"]
    assert "us.anthropic." not in snap["model_short"], "Bedrock prefix should be stripped"


def test_openrouter_model_shows_or_provider_badge(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    session_id = "bar-session-2"
    mod._record_runtime_state(
        session_id,
        {"profile_id": "tier_4", "display_name": "T4", "model": "z-ai/glm-5.2",
         "provider": "openrouter", "base_url": "https://openrouter.ai/api/v1", "api_mode": "chat_completions", "reasoning": "xhigh"},
        4,
    )
    cli = _make_cli_stub(mod, session_id, 4, "z-ai/glm-5.2")
    mod._patch_status_bar(cli)
    snap = cli._get_status_bar_snapshot()
    assert "[or|T4]" in snap["model_short"], f"Expected [or|T4] in {snap['model_short']!r}"
    assert "glm-5.2" in snap["model_short"]


def test_no_provider_in_state_shows_tier_only(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    session_id = "bar-session-3"
    with mod._state_lock:
        mod._last_tier[session_id] = 2
    cli = _make_cli_stub(mod, session_id, 2, "openai/gpt-5.4")
    mod._patch_status_bar(cli)
    snap = cli._get_status_bar_snapshot()
    assert "[T2]" in snap["model_short"], f"Expected [T2] in {snap['model_short']!r}"
    assert "gpt-5.4" in snap["model_short"]


def test_provider_short_map_is_complete_for_known_providers(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    for provider in ("bedrock", "openrouter", "openai-codex", "openai", "nous", "anthropic", "deepseek"):
        assert provider in mod._PROVIDER_SHORT, f"Missing entry for {provider!r} in _PROVIDER_SHORT"
