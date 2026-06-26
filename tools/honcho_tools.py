#!/usr/bin/env python3
"""
Honcho Tools Module

Provides direct tools for interacting with Honcho user modeling database.
These tools run side-by-side with the active external memory provider (Hindsight).

CRITICAL Rule: Use these tools ONLY when the user's query is explicitly about
stable user preferences, habits, workflow patterns, or persona context.
For general long-term recall, use Hindsight instead.
"""

import json
import logging
import threading
from typing import Any, Dict, List, Optional
from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)

_manager = None
_session_key = None
_lock = threading.Lock()


def _ensure_honcho(session_id: str):
    """Lazily initialize HonchoSessionManager and resolve session key."""
    global _manager, _session_key
    with _lock:
        if _manager is not None:
            return _manager, _session_key

        try:
            from plugins.memory.honcho.client import HonchoClientConfig, get_honcho_client
            from plugins.memory.honcho.session import HonchoSessionManager
        except ImportError as e:
            raise ImportError(
                "Honcho integration modules not found or honcho-ai package not installed. "
                f"Detail: {e}"
            )

        cfg = HonchoClientConfig.from_global_config()
        if not (cfg.api_key or cfg.base_url):
            raise ValueError(
                "Honcho not configured. Run 'hermes honcho setup' or set HONCHO_API_KEY."
            )

        client = get_honcho_client(cfg)
        _manager = HonchoSessionManager(
            honcho=client,
            config=cfg,
            context_tokens=cfg.context_tokens,
        )

        _session_key = cfg.resolve_session_name(
            session_title=None,
            session_id=session_id,
            gateway_session_key=None,
        ) or session_id or "hermes-default"

        _manager.get_or_create(_session_key)
        return _manager, _session_key


def honcho_profile_tool(args: Dict[str, Any], **kwargs) -> str:
    session_id = kwargs.get("session_id") or "hermes-default"
    try:
        manager, session_key = _ensure_honcho(session_id)
    except Exception as e:
        return tool_error(f"Honcho initialization failed: {e}")

    peer = args.get("peer", "user")
    card_update = args.get("card")

    try:
        if card_update:
            result = manager.set_peer_card(session_key, card_update, peer=peer)
            if result is None:
                return tool_error("Failed to update peer card.")
            return json.dumps({"result": f"Peer card updated ({len(result)} facts).", "card": result})

        card = manager.get_peer_card(session_key, peer=peer)
        if not card:
            return json.dumps({
                "hint": (
                    f"No facts found for peer '{peer}' yet. Facts accumulate "
                    "over time from observed conversation."
                )
            })
        return json.dumps({"result": card})
    except Exception as e:
        return tool_error(f"honcho_profile failed: {e}")


def honcho_search_tool(args: Dict[str, Any], **kwargs) -> str:
    session_id = kwargs.get("session_id") or "hermes-default"
    try:
        manager, session_key = _ensure_honcho(session_id)
    except Exception as e:
        return tool_error(f"Honcho initialization failed: {e}")

    query = args.get("query", "")
    if not query:
        return tool_error("Missing required parameter: query")

    max_tokens = min(int(args.get("max_tokens", 800)), 2000)
    peer = args.get("peer", "user")

    try:
        result = manager.search_context(session_key, query, max_tokens=max_tokens, peer=peer)
        if not result:
            return json.dumps({"result": "No relevant context found."})
        return json.dumps({"result": result})
    except Exception as e:
        return tool_error(f"honcho_search failed: {e}")


def honcho_context_tool(args: Dict[str, Any], **kwargs) -> str:
    session_id = kwargs.get("session_id") or "hermes-default"
    try:
        manager, session_key = _ensure_honcho(session_id)
    except Exception as e:
        return tool_error(f"Honcho initialization failed: {e}")

    peer = args.get("peer", "user")

    try:
        ctx = manager.get_session_context(session_key, peer=peer)
        if not ctx:
            return json.dumps({"result": "No context available yet."})

        parts = []
        if ctx.get("summary"):
            parts.append(f"## Summary\n{ctx['summary']}")
        if ctx.get("representation"):
            parts.append(f"## Representation\n{ctx['representation']}")
        if ctx.get("card"):
            parts.append(f"## Card\n{ctx['card']}")
        if ctx.get("recent_messages"):
            msgs = ctx["recent_messages"]
            msg_str = "\n".join(
                f"  [{m['role']}] {m['content'][:200]}"
                for m in msgs[-5:]
            )
            parts.append(f"## Recent messages\n{msg_str}")
        return json.dumps({"result": "\n\n".join(parts) or "No context available."})
    except Exception as e:
        return tool_error(f"honcho_context failed: {e}")


def honcho_conclude_tool(args: Dict[str, Any], **kwargs) -> str:
    session_id = kwargs.get("session_id") or "hermes-default"
    try:
        manager, session_key = _ensure_honcho(session_id)
    except Exception as e:
        return tool_error(f"Honcho initialization failed: {e}")

    delete_id = (args.get("delete_id") or "").strip()
    conclusion = args.get("conclusion", "").strip()
    peer = args.get("peer", "user")

    has_delete_id = bool(delete_id)
    has_conclusion = bool(conclusion)

    if has_delete_id == has_conclusion:
        return tool_error("Exactly one of conclusion or delete_id must be provided.")

    try:
        if has_delete_id:
            ok = manager.delete_conclusion(session_key, delete_id, peer=peer)
            if ok:
                return json.dumps({"result": f"Conclusion {delete_id} deleted."})
            return tool_error(f"Failed to delete conclusion {delete_id}.")

        ok = manager.create_conclusion(session_key, conclusion, peer=peer)
        if ok:
            return json.dumps({"result": f"Conclusion saved for {peer}: {conclusion}"})
        return tool_error("Failed to save conclusion.")
    except Exception as e:
        return tool_error(f"honcho_conclude failed: {e}")


def check_honcho_requirements() -> bool:
    try:
        from plugins.memory.honcho.client import HonchoClientConfig
        cfg = HonchoClientConfig.from_global_config()
        return bool(cfg.api_key or cfg.base_url)
    except Exception:
        return False


# =============================================================================
# OpenAI Function-Calling Schemas
# =============================================================================

PROFILE_SCHEMA = {
    "name": "honcho_profile",
    "description": (
        "Retrieve or update a peer card from Honcho — a curated list of key facts "
        "about that peer (name, role, preferences, communication style, patterns). "
        "Pass `card` to update; omit `card` to read.  "
        "CRITICAL: Use this tool ONLY when the user's query is explicitly about stable "
        "user preferences, habits, workflow patterns, or stable persona context. "
        "For general long-term recall, use hindsight instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "peer": {
                "type": "string",
                "description": "Peer to query. Built-in aliases: 'user' (default), 'ai'. Or pass any peer ID from this workspace.",
            },
            "card": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New peer card as a list of fact strings. Omit to read the current card.",
            },
        },
        "required": [],
    },
}

SEARCH_SCHEMA = {
    "name": "honcho_search",
    "description": (
        "Semantic search over Honcho's stored context about a peer. "
        "Returns raw excerpts ranked by relevance. "
        "CRITICAL: Use this tool ONLY when the user's query is explicitly about stable "
        "user preferences, habits, workflow patterns, or stable persona context. "
        "For general long-term recall, use hindsight instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for in Honcho's memory.",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Token budget for returned context (default 800, max 2000).",
            },
            "peer": {
                "type": "string",
                "description": "Peer to query. Built-in aliases: 'user' (default), 'ai'. Or pass any peer ID from this workspace.",
            },
        },
        "required": ["query"],
    },
}

CONTEXT_SCHEMA = {
    "name": "honcho_context",
    "description": (
        "Retrieve full session context from Honcho — summary, peer representation, "
        "peer card, and recent messages. No LLM synthesis. "
        "CRITICAL: Use this tool ONLY when the user's query is explicitly about stable "
        "user preferences, habits, workflow patterns, or stable persona context. "
        "For general long-term recall, use hindsight instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional focus query to filter context. Omit for full session context snapshot.",
            },
            "peer": {
                "type": "string",
                "description": "Peer to query. Built-in aliases: 'user' (default), 'ai'. Or pass any peer ID from this workspace.",
            },
        },
        "required": [],
    },
}

CONCLUDE_SCHEMA = {
    "name": "honcho_conclude",
    "description": (
        "Write or delete a conclusion about a peer in Honcho's memory. "
        "Conclusions are persistent facts that build a peer's profile. "
        "You MUST pass exactly one of: `conclusion` (to create) or `delete_id` (to delete). "
        "CRITICAL: Use this tool ONLY to store stable user preferences, habits, workflow patterns, "
        "or stable persona details. For general memory writes, use the standard memory tool instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "conclusion": {
                "type": "string",
                "description": "A factual statement to persist. Provide this when creating a conclusion. Do not send it together with delete_id.",
            },
            "delete_id": {
                "type": "string",
                "description": "Conclusion ID to delete for PII removal. Provide this when deleting a conclusion. Do not send it together with conclusion.",
            },
            "peer": {
                "type": "string",
                "description": "Peer to query. Built-in aliases: 'user' (default), 'ai'. Or pass any peer ID from this workspace.",
            },
        },
        "required": [],
    },
}

# --- Register Tools ---

registry.register(
    name="honcho_profile",
    toolset="honcho",
    schema=PROFILE_SCHEMA,
    handler=honcho_profile_tool,
    check_fn=check_honcho_requirements,
    emoji="👤",
)

registry.register(
    name="honcho_search",
    toolset="honcho",
    schema=SEARCH_SCHEMA,
    handler=honcho_search_tool,
    check_fn=check_honcho_requirements,
    emoji="🔍",
)

registry.register(
    name="honcho_context",
    toolset="honcho",
    schema=CONTEXT_SCHEMA,
    handler=honcho_context_tool,
    check_fn=check_honcho_requirements,
    emoji="📝",
)

registry.register(
    name="honcho_conclude",
    toolset="honcho",
    schema=CONCLUDE_SCHEMA,
    handler=honcho_conclude_tool,
    check_fn=check_honcho_requirements,
    emoji="💡",
)
