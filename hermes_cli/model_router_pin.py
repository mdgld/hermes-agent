"""Shared helpers for pinning manual model choices in model-router."""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)


def _get_model_router_manager():
    try:
        from hermes_cli.plugins import get_plugin_manager

        mgr = get_plugin_manager()
        if getattr(mgr, "router_pin_session", None) is None and hasattr(
            mgr, "discover_and_load"
        ):
            mgr.discover_and_load()
        return mgr
    except Exception:
        return None


async def _get_model_router_manager_async():
    try:
        from hermes_cli.plugins import get_plugin_manager

        mgr = get_plugin_manager()
        if getattr(mgr, "router_pin_session", None) is None and hasattr(
            mgr, "discover_and_load"
        ):
            import asyncio

            await asyncio.to_thread(mgr.discover_and_load)
        return mgr
    except Exception:
        return None


def pin_model_router_sessions(router_session_ids: Iterable[str], model: str) -> None:
    """Pin every known router session id to *model*, best-effort."""
    model = str(model or "").strip()
    if not model:
        return
    mgr = _get_model_router_manager()
    pin_fn = getattr(mgr, "router_pin_session", None) if mgr is not None else None
    if not callable(pin_fn):
        return
    seen: set[str] = set()
    for raw_sid in router_session_ids or []:
        sid = str(raw_sid or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        try:
            pin_fn(sid, model)
        except Exception:
            logger.debug(
                "failed to pin model-router session %s to %s",
                sid,
                model,
                exc_info=True,
            )


async def pin_model_router_sessions_async(
    router_session_ids: Iterable[str], model: str
) -> None:
    """Async gateway-safe variant of :func:`pin_model_router_sessions`."""
    model = str(model or "").strip()
    if not model:
        return
    mgr = await _get_model_router_manager_async()
    pin_fn = getattr(mgr, "router_pin_session", None) if mgr is not None else None
    if not callable(pin_fn):
        return
    seen: set[str] = set()
    for raw_sid in router_session_ids or []:
        sid = str(raw_sid or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        try:
            pin_fn(sid, model)
        except Exception:
            logger.debug(
                "failed to pin model-router session %s to %s",
                sid,
                model,
                exc_info=True,
            )
