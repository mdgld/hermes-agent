from datetime import datetime
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
    runner._session_db = None
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
async def test_router_status_surfaces_runtime_and_events(monkeypatch):
    runner = _make_runner()
    runner._session_model_overrides["gateway-session-key"] = {
        "model": "us.anthropic.claude-opus-4-8",
        "provider": "bedrock",
        "base_url": "",
        "api_mode": "bedrock_converse",
        "runtime_profile": "tier_4",
    }

    class _Mgr:
        def router_get_diagnostics(self, session_id, limit=5):
            assert session_id == "router-session-id"
            return {
                "session_id": session_id,
                "state": {
                    "pinned": True,
                    "tier": 4,
                    "profile_id": "tier_4",
                    "provider": "bedrock",
                    "model": "us.anthropic.claude-opus-4-8",
                    "api_mode": "bedrock_converse",
                    "reasoning": "xhigh",
                    "updated_at": 1775791440.0,
                },
                "recent_events": [
                    {"event": "session_pinned", "model": "us.anthropic.claude-opus-4-8"},
                    {"event": "runtime_state_updated", "tier": 4, "provider": "bedrock", "model": "us.anthropic.claude-opus-4-8"},
                ],
            }

    monkeypatch.setattr("hermes_cli.plugins.get_plugin_manager", lambda: _Mgr())

    result = await runner._handle_router_status_command(_make_event("/router-status"))

    assert "Hermes Router Status" in result
    assert "Mode: pinned" in result
    assert "Tier: T4" in result
    assert "Profile: tier_4" in result
    assert "bedrock" in result
    assert "runtime_state_updated · T4 · bedrock · us.anthropic.claude-opus-4-8" in result


@pytest.mark.asyncio
async def test_status_reports_router_override_mismatch(monkeypatch):
    runner = _make_runner()
    runner._session_model_overrides["gateway-session-key"] = {
        "model": "override-model",
        "provider": "bedrock",
        "base_url": "",
        "api_mode": "bedrock_converse",
        "runtime_profile": "tier_4",
    }

    class _Mgr:
        def router_get_diagnostics(self, session_id, limit=3):
            return {
                "session_id": session_id,
                "state": {
                    "pinned": True,
                    "tier": 4,
                    "profile_id": "tier_4",
                    "provider": "bedrock",
                    "model": "router-model",
                    "api_mode": "bedrock_converse",
                },
            }

    monkeypatch.setattr("hermes_cli.plugins.get_plugin_manager", lambda: _Mgr())
    monkeypatch.setattr("gateway.run._load_gateway_config", lambda: {})
    monkeypatch.setattr("gateway.run._resolve_gateway_model", lambda cfg=None: "default-model")

    result = await runner._handle_status_command(_make_event("/status"))

    assert "Router: pinned · T4 · tier_4 · bedrock · router-model · bedrock_converse" in result
    assert "Router Override Mismatch: gateway=override-model router=router-model" in result
