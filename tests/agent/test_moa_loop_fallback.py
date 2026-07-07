from types import SimpleNamespace

import pytest

from agent import moa_loop


def _response(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=None,
    )


class RetryableError(Exception):
    status_code = 429


class BadRequestError(Exception):
    status_code = 400


@pytest.fixture(autouse=True)
def stable_slot_runtime(monkeypatch):
    monkeypatch.setattr(
        moa_loop,
        "_slot_runtime",
        lambda slot: {"provider": slot["provider"], "model": slot["model"]},
    )


def test_reference_retryable_error_uses_reference_fallback(monkeypatch):
    calls = []

    def fake_call_llm(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "primary-ref":
            raise RetryableError("rate limited")
        return _response("fallback reference served")

    monkeypatch.setattr(moa_loop, "call_llm", fake_call_llm)

    label, text, acct = moa_loop._run_reference(
        {"provider": "openrouter", "model": "primary-ref"},
        [{"role": "user", "content": "task"}],
        reference_fallbacks=[{"provider": "openai-codex", "model": "fallback-ref"}],
    )

    assert calls == ["primary-ref", "fallback-ref"]
    assert label == "openrouter:primary-ref → fallback openai-codex:fallback-ref"
    assert text == "fallback reference served"
    assert acct.model == "fallback-ref"


def test_reference_non_retryable_error_does_not_consume_fallback(monkeypatch):
    calls = []

    def fake_call_llm(**kwargs):
        calls.append(kwargs["model"])
        raise BadRequestError("bad request")

    monkeypatch.setattr(moa_loop, "call_llm", fake_call_llm)

    label, text, _acct = moa_loop._run_reference(
        {"provider": "openrouter", "model": "primary-ref"},
        [{"role": "user", "content": "task"}],
        reference_fallbacks=[{"provider": "openai-codex", "model": "fallback-ref"}],
    )

    assert calls == ["primary-ref"]
    assert label == "openrouter:primary-ref"
    assert "bad request" in text


def test_create_retryable_aggregator_error_uses_aggregator_fallback(monkeypatch):
    calls = []

    def fake_load_config():
        return {
            "moa": {
                "default_preset": "p",
                "presets": {
                    "p": {
                        "reference_models": [],
                        "enabled": False,
                        "aggregator": {"provider": "openrouter", "model": "primary-agg"},
                        "aggregator_fallbacks": [
                            {"provider": "openai-codex", "model": "fallback-agg"}
                        ],
                    }
                },
            }
        }

    def fake_call_llm(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "primary-agg":
            raise RetryableError("rate limited")
        return _response("fallback aggregator served")

    import hermes_cli.config as config_mod

    monkeypatch.setattr(config_mod, "load_config", fake_load_config)
    monkeypatch.setattr(moa_loop, "call_llm", fake_call_llm)

    response = moa_loop.MoAChatCompletions("p").create(
        messages=[{"role": "user", "content": "task"}],
        stream=False,
    )

    assert calls == ["primary-agg", "fallback-agg"]
    assert moa_loop._extract_text(response) == "fallback aggregator served"


def test_empty_fallback_list_preserves_failure(monkeypatch):
    calls = []

    def fake_call_llm(**kwargs):
        calls.append(kwargs["model"])
        raise RetryableError("rate limited")

    monkeypatch.setattr(moa_loop, "call_llm", fake_call_llm)

    label, text, _acct = moa_loop._run_reference(
        {"provider": "openrouter", "model": "primary-ref"},
        [{"role": "user", "content": "task"}],
        reference_fallbacks=[],
    )

    assert calls == ["primary-ref"]
    assert label == "openrouter:primary-ref"
    assert "rate limited" in text
