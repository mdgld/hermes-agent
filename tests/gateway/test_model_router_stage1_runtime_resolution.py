from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionEntry, SessionSource


def _make_source() -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM,
        user_id="u1",
        chat_id="c1",
        user_name="tester",
        chat_type="dm",
    )


def _make_event(text: str) -> MessageEvent:
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=_make_source(),
        message_id="m1",
    )


def _make_runner():
    runner = object.__new__(GatewayRunner)
    runner.adapters = {Platform.TELEGRAM: MagicMock()}
    runner._session_model_overrides = {}
    runner._session_reasoning_overrides = {}
    runner._pending_model_notes = {}
    runner._running_agents = {}
    runner._agent_cache = {}
    runner._agent_cache_lock = None
    runner._session_db = MagicMock()
    runner._normalize_source_for_session_key = lambda source: source
    runner._session_key_for_source = lambda source: "gateway-session-key"
    runner._evict_cached_agent = MagicMock()
    runner._queue_depth = lambda session_key, adapter=None: 0
    runner.session_store = MagicMock()
    entry = SessionEntry(
        session_key="gateway-session-key",
        session_id="router-session-id",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner.session_store.get_or_create_session.return_value = entry
    runner.session_store._entries = {"gateway-session-key": entry}
    return runner


@pytest.mark.asyncio
async def test_tier_command_uses_router_session_id_and_stores_full_runtime(monkeypatch):
    runner = _make_runner()
    runtime = {
        "profile_id": "tier_4",
        "display_name": "T4 (Opus 4.8 - Bedrock)",
        "model": "us.anthropic.claude-opus-4-8",
        "provider": "bedrock",
        "base_url": "",
        "api_mode": "bedrock_converse",
        "reasoning": "xhigh",
    }
    seen = {}

    class _Mgr:
        def router_apply_tier(self, session_id, tier_num, current_model):
            seen["apply"] = (session_id, tier_num, current_model)
            return dict(runtime)

        def router_resolve_tier_runtime(self, tier_num):
            seen["resolve"] = tier_num
            return dict(runtime)

        def router_get_tier_meta(self, tier_num):
            return {"label": "T4", "model": runtime["model"]}

    monkeypatch.setattr("hermes_cli.plugins.get_plugin_manager", lambda: _Mgr())
    monkeypatch.setattr("gateway.run._load_gateway_config", lambda: {})
    monkeypatch.setattr("gateway.run._resolve_gateway_model", lambda cfg=None: "default-model")

    result = await runner._handle_tier_pin_command(_make_event("/t4"))

    assert seen["apply"] == ("router-session-id", 4, "default-model")
    assert seen["resolve"] == 4
    assert runner._session_model_overrides["gateway-session-key"] == {
        "model": "us.anthropic.claude-opus-4-8",
        "provider": "bedrock",
        "api_key": "",
        "base_url": "",
        "api_mode": "bedrock_converse",
        "runtime_profile": "tier_4",
    }
    assert runner._session_reasoning_overrides["gateway-session-key"] == {
        "enabled": True,
        "effort": "xhigh",
    }
    runner._session_db.update_session_model.assert_called_once_with(
        "router-session-id",
        "us.anthropic.claude-opus-4-8",
    )
    runner._evict_cached_agent.assert_called_once_with("gateway-session-key")
    assert "Pinned to T4 (Opus 4.8 - Bedrock)" in result


@pytest.mark.asyncio
async def test_auto_command_unpins_router_session_id_and_clears_session_state(monkeypatch):
    runner = _make_runner()
    runner._session_model_overrides["gateway-session-key"] = {
        "model": "us.anthropic.claude-opus-4-8",
        "provider": "bedrock",
        "api_key": "",
        "base_url": "",
        "api_mode": "bedrock_converse",
        "runtime_profile": "tier_4",
    }
    runner._session_reasoning_overrides["gateway-session-key"] = {
        "enabled": True,
        "effort": "xhigh",
    }
    runner._pending_model_notes["gateway-session-key"] = "[Note: pinned.]"
    seen = {}

    class _Mgr:
        def router_unpin_session(self, session_id):
            seen["unpin"] = session_id

        def router_is_pinned(self, session_id):
            seen["is_pinned"] = session_id
            return True

    monkeypatch.setattr("hermes_cli.plugins.get_plugin_manager", lambda: _Mgr())

    result = await runner._handle_auto_command(_make_event("/auto"))

    assert seen["is_pinned"] == "router-session-id"
    assert seen["unpin"] == "router-session-id"
    assert "gateway-session-key" not in runner._session_model_overrides
    assert "gateway-session-key" not in runner._session_reasoning_overrides
    assert "gateway-session-key" not in runner._pending_model_notes
    runner._evict_cached_agent.assert_called_once_with("gateway-session-key")
    assert "Auto model routing resumed" in result


@pytest.mark.asyncio
async def test_status_prefers_session_override_model_over_config(monkeypatch):
    runner = _make_runner()
    runner._session_db = None
    runner._session_model_overrides["gateway-session-key"] = {
        "model": "us.anthropic.claude-opus-4-8",
        "provider": "bedrock",
        "api_key": "",
        "base_url": "",
        "api_mode": "bedrock_converse",
        "runtime_profile": "tier_4",
    }
    monkeypatch.setattr("gateway.run._load_gateway_config", lambda: {"model": {"default": "wrong-model", "provider": "openrouter"}})
    monkeypatch.setattr("gateway.run._resolve_gateway_model", lambda cfg=None: "wrong-model")

    result = await runner._handle_status_command(_make_event("/status"))

    assert "us.anthropic.claude-opus-4-8" in result
    assert "bedrock" in result
    assert "wrong-model" not in result
