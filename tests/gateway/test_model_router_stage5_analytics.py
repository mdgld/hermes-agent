"""Stage 5 tests: analytics aggregation and eval fixture runner."""
import importlib.util
import json
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
    mod._manager_ref = None
    return mod, hermes_home


def _write_events(hermes_home: Path, events: list[dict]) -> None:
    events_dir = hermes_home / "model-router"
    events_dir.mkdir(parents=True, exist_ok=True)
    events_path = events_dir / "events.jsonl"
    with events_path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def test_analytics_aggregates_event_log_correctly(tmp_path, monkeypatch):
    mod, hermes_home = _load_plugin(tmp_path, monkeypatch)
    _write_events(hermes_home, [
        {"ts": 1.0, "event": "route_decision", "session_id": "s1", "reason": "task_route", "tier": 5, "provider": "nous", "route_name": "security"},
        {"ts": 2.0, "event": "route_decision", "session_id": "s2", "reason": "task_route", "tier": 5, "provider": "nous", "route_name": "security"},
        {"ts": 3.0, "event": "route_decision", "session_id": "s3", "reason": "classifier", "tier": 3, "provider": "openrouter"},
        {"ts": 4.0, "event": "classifier_fallback", "session_id": "", "reason": "all_providers_exhausted", "safe_tier": 2},
        {"ts": 5.0, "event": "route_decision", "session_id": "s4", "reason": "explicit_tier", "tier": 4, "provider": "nous"},
    ])
    data = mod.get_router_analytics(limit=100)
    assert data["total_events_read"] == 5
    assert data["tier_counts"].get(5) == 2
    assert data["tier_counts"].get(3) == 1
    assert data["tier_counts"].get(4) == 1
    assert data["reason_counts"].get("task_route") == 2
    assert data["reason_counts"].get("classifier") == 1
    assert data["reason_counts"].get("explicit_tier") == 1
    assert data["task_route_hits"].get("security") == 2
    assert data["provider_counts"].get("nous") == 3
    assert data["classifier_fallback_count"] == 1
    assert data["mismatch_count"] == 0


def test_analytics_ignores_malformed_lines(tmp_path, monkeypatch):
    mod, hermes_home = _load_plugin(tmp_path, monkeypatch)
    events_dir = hermes_home / "model-router"
    events_dir.mkdir(parents=True, exist_ok=True)
    events_path = events_dir / "events.jsonl"
    with events_path.open("w", encoding="utf-8") as fh:
        fh.write("not valid json\n")
        fh.write("{broken\n")
        fh.write(json.dumps({"ts": 1.0, "event": "route_decision", "session_id": "s1", "reason": "ack", "tier": 1, "provider": "nous"}) + "\n")
        fh.write("\n")
    data = mod.get_router_analytics(limit=100)
    assert data["total_events_read"] == 1
    assert data["tier_counts"].get(1) == 1


def test_eval_fixture_runner_reports_expected_routes(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    result = mod.eval_task_routing()
    assert isinstance(result, dict)
    assert result["total"] > 0
    assert "passed" in result
    assert "failed" in result
    assert "results" in result
    assert result["passed"] > 0, f"Expected some fixtures to pass, got: {result}"
    for item in result["results"]:
        assert "prompt" in item
        assert "expected_tier" in item
        assert "actual_tier" in item
        assert "pass" in item


def test_eval_fixture_runner_with_custom_fixtures(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    fixtures = [
        {"prompt": "ok", "expected_tier": 1, "expected_reason": "ack"},
        {"prompt": "T4 plan this refactor", "expected_tier": 4, "expected_reason": "explicit_tier"},
        {"prompt": "security vulnerability audit", "expected_tier": 5, "expected_reason": "task_route"},
    ]
    result = mod.eval_task_routing(fixtures=fixtures)
    assert result["total"] == 3
    assert result["passed"] == 3, f"Expected all 3 to pass: {result['results']}"
    assert result["failed"] == 0


def test_analytics_returns_empty_counts_for_no_events(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    data = mod.get_router_analytics(limit=100)
    assert data["total_events_read"] == 0
    assert data["tier_counts"] == {}
    assert data["reason_counts"] == {}
    assert data["classifier_fallback_count"] == 0
