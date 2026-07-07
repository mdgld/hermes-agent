from hermes_cli.model_switch import switch_model
from hermes_cli.models import detect_static_provider_for_model


def test_bare_moa_is_not_implicit_provider_switch():
    assert detect_static_provider_for_model("moa", "openrouter") is None


def test_bare_default_does_not_activate_moa_preset():
    result = switch_model(
        raw_input="default",
        current_provider="openrouter",
        current_model="openai/gpt-5.5",
        current_base_url="",
        current_api_key="test-key",
        is_global=False,
    )

    assert result.target_provider != "moa"
    assert not result.success
    assert "not found" in (result.error_message or "")


def test_explicit_moa_prefix_activates_default_preset():
    result = switch_model(
        raw_input="moa:",
        current_provider="openrouter",
        current_model="openai/gpt-5.5",
        current_base_url="",
        current_api_key="test-key",
        is_global=False,
    )

    assert result.success
    assert result.target_provider == "moa"
    assert result.new_model == "default"
