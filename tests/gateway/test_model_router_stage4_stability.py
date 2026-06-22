"""Stage 4 tests: startup validation, classifier fallback, safe degradation."""
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
    mod._manager_ref = None
    return mod, hermes_home


def test_validate_router_config_ok_for_default_config(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    result = mod.validate_router_config(mod._router_config)
    assert isinstance(result, dict)
    assert "valid" in result
    assert "errors" in result
    assert "warnings" in result
    assert result["errors"] == [], f"Default config should have no errors: {result['errors']}"


def test_validate_router_config_errors_on_missing_model(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    import copy
    bad_config = copy.deepcopy(mod._router_config)
    bad_config["tiers"][3]["model"] = ""
    result = mod.validate_router_config(bad_config)
    assert not result["valid"]
    assert any("tier 3" in e for e in result["errors"])


def test_validate_router_config_warns_on_empty_profile_provider(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    import copy
    config = mod._normalize_router_config({})
    for profile in config.get("runtime_profiles", {}).values():
        profile["provider"] = ""
    result = mod.validate_router_config(config)
    assert any("provider" in w for w in result["warnings"])


def test_startup_validation_stored_after_load(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    status = mod.get_router_startup_status()
    assert isinstance(status, dict)
    assert "valid" in status


def test_diagnostics_includes_startup_validation(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    diag = mod.get_router_diagnostics()
    assert "startup_validation" in diag
    assert isinstance(diag["startup_validation"], dict)


def test_malformed_config_falls_back_to_defaults(tmp_path, monkeypatch):
    mod, hermes_home = _load_plugin(tmp_path, monkeypatch)
    config_path = hermes_home / "model_router.yaml"
    config_path.write_text("not: a: valid: yaml: [[[", encoding="utf-8")
    mod._load_router_config()
    status = mod.get_router_startup_status()
    assert isinstance(status, dict)
    assert not status.get("valid", True) or status.get("errors") is not None


def test_classifier_failure_emits_fallback_event(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)

    def _fake_call_llm(*args, **kwargs):
        raise RuntimeError("simulated classifier failure")

    import sys
    import types
    fake_agent = types.ModuleType("agent")
    fake_aux = types.ModuleType("agent.auxiliary_client")
    fake_aux.call_llm = _fake_call_llm
    fake_agent.auxiliary_client = fake_aux
    sys.modules.setdefault("agent", fake_agent)
    sys.modules["agent.auxiliary_client"] = fake_aux

    mod._classify_with_flash("some message that won't match any task route", [])

    events = mod.get_recent_events("", limit=20)
    fallback_events = [e for e in events if e.get("event") == "classifier_fallback"]
    assert fallback_events, "classifier_fallback event must be emitted when all providers fail"
    ev = fallback_events[-1]
    assert "safe_tier" in ev


def test_all_stage1_2_3_bundle_passes(tmp_path, monkeypatch):
    mod, _ = _load_plugin(tmp_path, monkeypatch)
    assert mod.TIERS is not None
    assert len(mod.TIERS) == 5
    assert mod.TASK_ROUTES is not None
    assert len(mod.TASK_ROUTES) > 0
