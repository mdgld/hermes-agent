"""Nous Portal provider profile."""

from typing import Any

from agent.portal_tags import nous_portal_tags
from providers import register_provider
from providers.base import ProviderProfile


def _is_mimo_model(model: str | None) -> bool:
    """Check if the model is a MiMo model (needs thinking.type instead of reasoning)."""
    m = (model or "").strip().lower()
    return "mimo" in m


class NousProfile(ProviderProfile):
    """Nous Portal — product tags, reasoning with Nous-specific omission."""

    def build_extra_body(
        self, *, session_id: str | None = None, **context
    ) -> dict[str, Any]:
        return {"tags": nous_portal_tags()}

    def build_api_kwargs_extras(
        self,
        *,
        reasoning_config: dict | None = None,
        supports_reasoning: bool = False,
        model: str | None = None,
        **context,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Nous: passes reasoning config, with MiMo-specific handling.

        MiMo models require ``extra_body.thinking.type`` (``enabled``/``disabled``)
        instead of the ``reasoning`` dict that other Nous models use.
        """
        extra_body: dict[str, Any] = {}

        if not supports_reasoning:
            return extra_body, {}

        if _is_mimo_model(model):
            # MiMo uses thinking.type: enabled/disabled
            if isinstance(reasoning_config, dict) and reasoning_config.get("enabled") is False:
                extra_body["thinking"] = {"type": "disabled"}
            else:
                extra_body["thinking"] = {"type": "enabled"}
        else:
            # Non-MiMo Nous models use the reasoning dict (existing behavior)
            if reasoning_config is not None:
                rc = dict(reasoning_config)
                if rc.get("enabled") is False:
                    pass  # Nous omits reasoning when disabled
                else:
                    extra_body["reasoning"] = rc
            else:
                extra_body["reasoning"] = {"enabled": True, "effort": "medium"}

        return extra_body, {}


nous = NousProfile(
    name="nous",
    aliases=("nous-portal", "nousresearch"),
    env_vars=("NOUS_API_KEY",),
    display_name="Nous Research",
    description="Nous Research — Hermes model family",
    signup_url="https://nousresearch.com/",
    fallback_models=(
        "hermes-3-405b",
        "hermes-3-70b",
    ),
    base_url="https://inference.nousresearch.com/v1",
    auth_type="oauth_device_code",
)

register_provider(nous)
