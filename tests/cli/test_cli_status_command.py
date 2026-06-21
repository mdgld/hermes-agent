"""Tests for CLI /status command behavior."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cli import HermesCLI
from hermes_cli.commands import resolve_command


def _make_cli():
    cli_obj = HermesCLI.__new__(HermesCLI)
    cli_obj.config = {}
    cli_obj.console = MagicMock()
    cli_obj.agent = None
    cli_obj.conversation_history = []
    cli_obj.session_id = "session-123"
    cli_obj._pending_input = MagicMock()
    cli_obj._status_bar_visible = True
    cli_obj.model = "openai/gpt-5.4"
    cli_obj.provider = "openai"
    cli_obj.session_start = datetime(2026, 4, 9, 19, 24)
    cli_obj._agent_running = False
    cli_obj._session_db = MagicMock()
    cli_obj._session_db.get_session.return_value = None
    return cli_obj


def test_status_command_is_available_in_cli_registry():
    cmd = resolve_command("status")
    assert cmd is not None
    assert cmd.gateway_only is False


def test_router_status_command_is_available_in_cli_registry():
    cmd = resolve_command("router-status")
    assert cmd is not None
    assert cmd.gateway_only is False


def test_process_command_status_dispatches_without_toggling_status_bar():
    cli_obj = _make_cli()

    with patch.object(cli_obj, "_show_session_status", create=True) as mock_status:
        assert cli_obj.process_command("/status") is True

    mock_status.assert_called_once_with()
    assert cli_obj._status_bar_visible is True


def test_process_command_router_status_dispatches():
    cli_obj = _make_cli()

    with patch.object(cli_obj, "_show_router_status", create=True) as mock_status:
        assert cli_obj.process_command("/router-status") is True

    mock_status.assert_called_once_with()


def test_statusbar_still_toggles_visibility():
    cli_obj = _make_cli()

    assert cli_obj.process_command("/statusbar") is True
    assert cli_obj._status_bar_visible is False


def test_status_prefix_prefers_status_command_over_statusbar_toggle():
    cli_obj = _make_cli()

    with patch.object(cli_obj, "_show_session_status") as mock_status:
        assert cli_obj.process_command("/sta") is True

    mock_status.assert_called_once_with()
    assert cli_obj._status_bar_visible is True


def test_show_session_status_prints_gateway_style_summary():
    cli_obj = _make_cli()
    cli_obj.agent = SimpleNamespace(
        session_total_tokens=321,
        session_api_calls=4,
    )
    cli_obj._session_db.get_session.return_value = {
        "title": "My titled session",
        "started_at": 1775791440,
    }

    with patch("cli.display_hermes_home", return_value="~/.hermes"):
        cli_obj._show_session_status()

    printed = "\n".join(str(call.args[0]) for call in cli_obj.console.print.call_args_list)
    assert "Hermes CLI Status" in printed
    assert "Session ID: session-123" in printed
    assert "Path: ~/.hermes" in printed
    assert "Title: My titled session" in printed
    assert "Model: openai/gpt-5.4 (openai)" in printed
    assert "Tokens: 321" in printed
    assert "Agent Running: No" in printed
    _, kwargs = cli_obj.console.print.call_args
    assert kwargs.get("highlight") is False
    assert kwargs.get("markup") is False


def test_show_session_status_includes_router_summary():
    cli_obj = _make_cli()
    cli_obj.agent = SimpleNamespace(session_total_tokens=0)

    with patch("cli.display_hermes_home", return_value="~/.hermes"), patch.object(
        cli_obj,
        "_get_router_state",
        return_value={
            "pinned": True,
            "tier": 4,
            "profile_id": "tier_4",
            "provider": "bedrock",
            "model": "us.anthropic.claude-opus-4-8",
        },
    ):
        cli_obj._show_session_status()

    printed = "\n".join(str(call.args[0]) for call in cli_obj.console.print.call_args_list)
    assert "Router: pinned · T4 · tier_4 · bedrock · us.anthropic.claude-opus-4-8" in printed


def test_show_router_status_prints_diagnostics():
    cli_obj = _make_cli()
    with patch.object(
        cli_obj,
        "_get_router_diagnostics",
        return_value={
            "state": {
                "pinned": True,
                "tier": 5,
                "profile_id": "tier_5",
                "provider": "openrouter",
                "model": "openai/gpt-latest",
                "api_mode": "chat_completions",
                "reasoning": "high",
                "updated_at": 1775791440.0,
            },
            "recent_events": [
                {"event": "session_pinned", "model": "openai/gpt-latest"},
                {"event": "runtime_state_updated", "tier": 5, "provider": "openrouter", "model": "openai/gpt-latest"},
            ],
        },
    ):
        cli_obj._show_router_status()

    printed = "\n".join(str(call.args[0]) for call in cli_obj.console.print.call_args_list)
    assert "Hermes Router Status" in printed
    assert "Tier: T5" in printed
    assert "Profile: tier_5" in printed
    assert "runtime_state_updated · T5 · openrouter · openai/gpt-latest" in printed


def test_profile_command_reports_custom_root_profile(monkeypatch, tmp_path, capsys):
    """Profile detection works for custom-root deployments (not under ~/.hermes)."""
    cli_obj = _make_cli()
    profile_home = tmp_path / "profiles" / "coder"

    monkeypatch.setenv("HERMES_HOME", str(profile_home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "unrelated-home")

    cli_obj._handle_profile_command()

    out = capsys.readouterr().out
    assert "Profile: coder" in out
    assert f"Home:    {profile_home}" in out


def test_router_config_command_is_available_in_cli_registry():
    cmd = resolve_command("router-config")
    assert cmd is not None
    assert cmd.gateway_only is False


def test_process_command_router_config_dispatches():
    cli_obj = _make_cli()

    with patch.object(cli_obj, "_show_router_config", create=True) as mock_config:
        assert cli_obj.process_command("/router-config") is True

    mock_config.assert_called_once_with()


def test_show_router_config_prints_tier_summary():
    cli_obj = _make_cli()
    with patch.object(
        cli_obj,
        "_get_router_diagnostics",
        return_value={},
    ), patch.object(
        cli_obj,
        "_get_router_manager",
        return_value=type("_Mgr", (), {
            "router_get_tier_meta": lambda self, t: {
                "label": f"T{t} test",
                "model": f"test-model-t{t}",
                "provider": "bedrock",
                "reasoning": "xhigh",
            },
            "router_get_startup_status": lambda self: {"valid": True, "errors": [], "warnings": []},
        })(),
    ):
        cli_obj._show_router_config()

    printed = "\n".join(str(call.args[0]) for call in cli_obj.console.print.call_args_list)
    assert "Hermes Router Config" in printed
    assert "T1 test" in printed
    assert "T5 test" in printed
    assert "bedrock" in printed
