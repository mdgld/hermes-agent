import importlib.util
import uuid
from pathlib import Path


PLUGIN_PATH = Path("/Users/matthewgold/.hermes/plugins/model-router/__init__.py")


def _load_plugin_module(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    module_name = f"test_model_router_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, hermes_home


def test_normalize_router_config_builds_runtime_profiles(tmp_path, monkeypatch):
    module, _ = _load_plugin_module(tmp_path, monkeypatch)

    config = module._normalize_router_config(
        {
            "tiers": {
                4: {
                    "label": "T4 Bedrock",
                    "target": "bedrock_opus",
                    "provider": "bedrock",
                    "model": "us.anthropic.claude-opus-4-8",
                    "reasoning": "xhigh",
                }
            },
            "runtime_profiles": {
                "bedrock_opus": {
                    "display_name": "Opus 4.8 on Bedrock",
                    "provider": "bedrock",
                    "wire_model": "us.anthropic.claude-opus-4-8",
                    "api_mode": "bedrock_converse",
                }
            },
        }
    )

    profile = config["runtime_profiles"]["bedrock_opus"]
    assert config["tiers"][4]["target"] == "bedrock_opus"
    assert profile["display_name"] == "Opus 4.8 on Bedrock"
    assert profile["wire_model"] == "us.anthropic.claude-opus-4-8"
    assert profile["api_mode"] == "bedrock_converse"


def test_persisted_state_round_trip(tmp_path, monkeypatch):
    module, hermes_home = _load_plugin_module(tmp_path, monkeypatch)

    module.pin_session("session-1", "model-a")
    module._record_runtime_state(
        "session-1",
        {
            "profile_id": "tier_4",
            "display_name": "T4",
            "model": "model-a",
            "provider": "bedrock",
            "base_url": "",
            "api_mode": "bedrock_converse",
            "reasoning": "xhigh",
        },
        4,
    )

    module._session_manual.clear()
    module._session_pinned.clear()
    module._last_tier.clear()
    module._base_tier.clear()
    module._session_runtime_state.clear()

    module._load_persisted_state()

    state_path = hermes_home / "model-router" / "state.json"
    assert state_path.exists()
    assert module.is_session_pinned("session-1") is True
    state = module.get_session_state("session-1")
    assert state["tier"] == 4
    assert state["profile_id"] == "tier_4"
    assert state["provider"] == "bedrock"


def test_router_events_and_diagnostics_round_trip(tmp_path, monkeypatch):
    module, hermes_home = _load_plugin_module(tmp_path, monkeypatch)

    runtime = {
        "profile_id": "tier_5",
        "display_name": "T5",
        "model": "openai/gpt-latest",
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_mode": "chat_completions",
        "reasoning": "high",
    }

    module.pin_session("session-2", runtime["model"])
    module._record_runtime_state("session-2", runtime, 5)

    events_path = hermes_home / "model-router" / "events.jsonl"
    assert events_path.exists()

    events = module.get_recent_events("session-2", limit=5)
    assert [event["event"] for event in events][-2:] == [
        "session_pinned",
        "runtime_state_updated",
    ]

    diagnostics = module.get_router_diagnostics("session-2", limit=5)
    assert diagnostics["session_id"] == "session-2"
    assert diagnostics["tier"] == 5
    assert diagnostics["profile_id"] == "tier_5"
    assert diagnostics["provider"] == "openrouter"
    assert len(diagnostics["recent_events"]) >= 2


def test_notify_manual_override_updates_tier_for_known_model(tmp_path, monkeypatch):
    module, _ = _load_plugin_module(tmp_path, monkeypatch)
    # Pick a model that lives in the default config's MODEL_TO_TIER map.
    # DEFAULT_ROUTER_CONFIG T1 model → should resolve to tier 1.
    t1_model = module.DEFAULT_ROUTER_CONFIG["tiers"][1]["model"]
    assert t1_model in module.MODEL_TO_TIER, "precondition: T1 model must be in MODEL_TO_TIER"
    module.notify_manual_override("sess-override-a", t1_model)
    assert module.is_session_pinned("sess-override-a")
    assert module.get_last_tier("sess-override-a") == 1


def test_notify_manual_override_does_not_crash_for_unknown_model(tmp_path, monkeypatch):
    module, _ = _load_plugin_module(tmp_path, monkeypatch)
    module.notify_manual_override("sess-override-b", "totally/unknown-model-xyz")
    assert module.is_session_pinned("sess-override-b")
    assert module.get_last_tier("sess-override-b") == 0
