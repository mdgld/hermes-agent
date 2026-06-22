"""Stage 3 tests: task-based routing + route trace."""
import importlib.util
import uuid
from pathlib import Path

import pytest

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
    # register() is not called in tests — initialize manager ref so _get_live_agent
    # short-circuits cleanly instead of raising NameError.
    mod._manager_ref = None
    return mod, hermes_home


def test_security_keyword_routes_t5_without_flash(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    flash_called = []
    monkeypatch.setattr(mod, "_classify_with_flash", lambda msg, hist: flash_called.append(1) or 2)
    result = mod.prepare_turn(
        session_id="s1",
        user_message="Review the security vulnerability in this auth module",
        conversation_history=[],
        current_model="",
        platform="test",
        apply_live=False,
    )
    assert result["tier"] == 5
    assert not flash_called, "Flash should NOT be called when task route matches"


def test_performance_keyword_routes_t5_without_flash(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    flash_called = []
    monkeypatch.setattr(mod, "_classify_with_flash", lambda msg, hist: flash_called.append(1) or 2)
    result = mod.prepare_turn(
        session_id="s2",
        user_message="How do I optimize the performance of this algorithm?",
        conversation_history=[],
        current_model="",
        platform="test",
        apply_live=False,
    )
    assert result["tier"] == 5
    assert not flash_called


def test_architecture_keyword_routes_t4_without_flash(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    flash_called = []
    monkeypatch.setattr(mod, "_classify_with_flash", lambda msg, hist: flash_called.append(1) or 2)
    result = mod.prepare_turn(
        session_id="s3",
        user_message="Help me plan the architecture for this migration",
        conversation_history=[],
        current_model="",
        platform="test",
        apply_live=False,
    )
    assert result["tier"] == 4
    assert not flash_called


def test_explicit_tier_overrides_task_route(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    flash_called = []
    monkeypatch.setattr(mod, "_classify_with_flash", lambda msg, hist: flash_called.append(1) or 3)
    # "T2" explicit + "security" keyword — explicit wins
    result = mod.prepare_turn(
        session_id="s4",
        user_message="T2 quick question about security concepts",
        conversation_history=[],
        current_model="",
        platform="test",
        apply_live=False,
    )
    assert result["tier"] == 2
    assert not flash_called


def test_ack_routes_t1_despite_keywords(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    flash_called = []
    monkeypatch.setattr(mod, "_classify_with_flash", lambda msg, hist: flash_called.append(1) or 3)
    result = mod.prepare_turn(
        session_id="s5",
        user_message="ok",
        conversation_history=[],
        current_model="",
        platform="test",
        apply_live=False,
    )
    assert result["tier"] == 1
    assert not flash_called


def test_get_session_state_returns_route_reason(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_classify_with_flash", lambda msg, hist: 2)
    mod.prepare_turn(
        session_id="s6",
        user_message="Review the security vulnerability in this auth module",
        conversation_history=[],
        current_model="",
        platform="test",
        apply_live=False,
    )
    state = mod.get_session_state("s6")
    assert state.get("route_reason") == "task_route"
    assert state.get("route_name") == "security"
    assert state.get("route_keyword") is not None


def test_get_router_diagnostics_returns_route_fields(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_classify_with_flash", lambda msg, hist: 2)
    mod._record_runtime_state(
        "s7",
        {
            "profile_id": "tier_5",
            "display_name": "T5",
            "model": "gpt-latest",
            "provider": "openrouter",
            "base_url": "",
            "api_mode": "chat_completions",
            "reasoning": "high",
        },
        5,
    )
    mod.prepare_turn(
        session_id="s7",
        user_message="Analyze the security exploit in this code",
        conversation_history=[],
        current_model="",
        platform="test",
        apply_live=False,
    )
    diag = mod.get_router_diagnostics("s7")
    assert diag.get("route_reason") == "task_route"
    assert diag.get("route_name") is not None


def test_route_decision_event_is_emitted(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_classify_with_flash", lambda msg, hist: 2)
    mod.prepare_turn(
        session_id="s8",
        user_message="security vulnerability in the authentication module",
        conversation_history=[],
        current_model="",
        platform="test",
        apply_live=False,
    )
    events = mod.get_recent_events("s8", limit=20)
    route_events = [e for e in events if e.get("event") == "route_decision"]
    assert route_events, "route_decision event must be emitted"
    ev = route_events[-1]
    assert ev["reason"] == "task_route"
    assert ev["tier"] == 5
    assert ev.get("route_name") == "security"
