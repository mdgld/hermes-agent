#!/usr/bin/env python3
"""
Chronos Tool Module - Custom Temporal Retrieval Framework

Implements a dual-index temporal retrieval framework with:
  - Event Calendar: structured SQLite database (`chronos.db` under HERMES_HOME)
    storing SVO event tuples with resolved time windows.
  - Turn Calendar: raw conversational messages from the session database (`state.db`).

Uses OpenRouter (openai/gpt-4.1-nano) asynchronously in the background after
each turn to extract events and index them.
"""

import json
import logging
import os
import sqlite3
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from hermes_constants import get_hermes_home
from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)


def _get_db_path() -> Path:
    """Return the path to the Chronos database file."""
    return get_hermes_home() / "chronos.db"


def init_db():
    """Initialize the SQLite database and create the event calendar schema."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chronos_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_id TEXT,
                event_timestamp REAL NOT NULL,
                subject TEXT,
                verb TEXT,
                object TEXT,
                event_text TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                entity_aliases TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chronos_events_session ON chronos_events(session_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chronos_events_time ON chronos_events(event_timestamp);")
        conn.commit()
    finally:
        conn.close()


def _get_openrouter_key() -> str:
    """Retrieve OpenRouter API key from environment or ~/.hermes/.env."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    env_path = get_hermes_home() / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("OPENROUTER_API_KEY="):
                        val = line.split("=", 1)[1].strip()
                        if val.startswith(('"', "'")) and val.endswith(('"', "'")):
                            val = val[1:-1]
                        return val
        except Exception:
            pass
    return ""


def _extract_and_index_events(user_text: str, assistant_text: str, session_id: str, turn_id: str, timestamp: float):
    """Call OpenRouter asynchronously to extract SVO event tuples and write them to SQLite."""
    try:
        api_key = _get_openrouter_key()
        if not api_key:
            logger.debug("Chronos: No OpenRouter API key found, skipping event extraction.")
            return

        prompt = f"""You are an event extraction parser for a conversational agent's memory.
Analyze the following conversation turn between a User and an AI Assistant.
Extract any notable events, facts, or actions discussed, especially those with a specific temporal grounding (e.g., scheduled meetings, actions performed, decisions made, plans).

Format the output strictly as a JSON list of objects, where each object represents an event and contains these keys:
- "subject": The subject performing the action.
- "verb": The action performed.
- "object": The object/recipient of the action.
- "event_text": A concise, natural language sentence describing the event.
- "start_time": An ISO-8601 string or date/time window indicating when the event occurred/starts (e.g. "2026-06-24T10:00:00"), or null if not specified.
- "end_time": When the event ends, or null.
- "entity_aliases": A list of names or entity identifiers involved in this event (e.g. ["User", "Vite", "Next.js"]).

If no notable events occurred in this turn, return an empty JSON list [].

Conversation Turn:
User: {user_text}
Assistant: {assistant_text}"""

        req_data = {
            "model": "openai/gpt-4.1-nano",
            "messages": [
                {"role": "system", "content": "You are a precise SVO event extraction helper. Always return valid JSON, and nothing else."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(req_data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            content = res_json["choices"][0]["message"]["content"].strip()

        # Sanity check JSON markdown wrap
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        events = json.loads(content)
        if isinstance(events, dict):
            for key in ["events", "list", "data"]:
                if key in events and isinstance(events[key], list):
                    events = events[key]
                    break

        if not isinstance(events, list):
            logger.debug("Chronos: SVO extraction did not return a valid list structure.")
            return

        db_path = _get_db_path()
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.cursor()
            for ev in events:
                if not isinstance(ev, dict) or "event_text" not in ev:
                    continue
                subject = ev.get("subject")
                verb = ev.get("verb")
                obj = ev.get("object")
                event_text = ev["event_text"]
                start_time = ev.get("start_time")
                end_time = ev.get("end_time")
                entity_aliases = json.dumps(ev.get("entity_aliases") or [])

                cursor.execute("""
                    INSERT INTO chronos_events (session_id, turn_id, event_timestamp, subject, verb, object, event_text, start_time, end_time, entity_aliases)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (session_id, turn_id, timestamp, subject, verb, obj, event_text, start_time, end_time, entity_aliases))
            conn.commit()
            logger.info("Chronos: Successfully indexed %d events for session %s.", len(events), session_id)
        finally:
            conn.close()

    except Exception as e:
        logger.error("Chronos: SVO event extraction background thread failed: %s", e, exc_info=True)


def queue_chronos_extraction(user_text: str, assistant_text: str, session_id: str, turn_id: str, timestamp: float | None = None):
    """Enqueue SVO event extraction on a background thread."""
    init_db()
    if timestamp is None:
        timestamp = time.time()
    t = threading.Thread(
        target=_extract_and_index_events,
        args=(user_text, assistant_text, session_id, turn_id, timestamp),
        daemon=True,
        name="chronos-extraction"
    )
    t.start()


def chronos_query_tool(args: Dict[str, Any], **kwargs) -> str:
    """Query the event calendar, and resolve raw Turn Calendar context from state.db."""
    session_id = kwargs.get("session_id") or "hermes-default"
    query = args.get("query", "").strip()
    start_time = args.get("start_time")
    end_time = args.get("end_time")
    limit = min(int(args.get("limit", 5)), 20)

    db_path = _get_db_path()
    if not db_path.exists():
        return json.dumps({"result": "Chronos temporal database is empty. No events indexed yet."})

    init_db()
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        sql = "SELECT id, session_id, event_timestamp, subject, verb, object, event_text, start_time, end_time, entity_aliases FROM chronos_events WHERE 1=1"
        params = []

        if query:
            sql += " AND (event_text LIKE ? OR subject LIKE ? OR verb LIKE ? OR object LIKE ? OR entity_aliases LIKE ?)"
            q_param = f"%{query}%"
            params.extend([q_param, q_param, q_param, q_param, q_param])
        if start_time:
            sql += " AND (start_time >= ? OR event_timestamp >= ?)"
            params.extend([start_time, start_time])
        if end_time:
            sql += " AND (end_time <= ? OR event_timestamp <= ?)"
            params.extend([end_time, end_time])

        sql += " ORDER BY event_timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()

        if not rows:
            return json.dumps({"result": "No matching events found in Event Calendar."})

        # Load turn context from state.db using SessionDB
        from hermes_state import SessionDB
        try:
            state_db = SessionDB()
        except Exception:
            state_db = None

        events = []
        for row in rows:
            ev_id, ev_session, ev_ts, sub, verb, obj, text, start, end, entities = row
            ev_info = {
                "event_id": ev_id,
                "session_id": ev_session,
                "event_text": text,
                "subject": sub,
                "verb": verb,
                "object": obj,
                "start_time": start,
                "end_time": end,
                "entities": json.loads(entities or "[]"),
                "timestamp": ev_ts
            }

            # Fetch +/- 60 seconds of turn calendar context from state.db
            context_messages = []
            if state_db:
                try:
                    c = state_db._conn.cursor()
                    c.execute("""
                        SELECT role, content, timestamp FROM messages 
                        WHERE session_id = ? AND timestamp BETWEEN ? AND ?
                        ORDER BY timestamp ASC LIMIT 5
                    """, (ev_session, ev_ts - 60, ev_ts + 60))
                    msg_rows = c.fetchall()
                    for m_role, m_content, m_ts in msg_rows:
                        context_messages.append({
                            "role": m_role,
                            "content": m_content,
                            "timestamp": m_ts
                        })
                except Exception as e:
                    logger.debug("Chronos: Failed to query messages around event timestamp: %s", e)

            ev_info["conversation_context"] = context_messages
            events.append(ev_info)

        return json.dumps({"events": events}, indent=2, ensure_ascii=False)
    finally:
        conn.close()


def chronos_list_events_tool(args: Dict[str, Any], **kwargs) -> str:
    """List events in the Event Calendar filtered by temporal range and/or entities."""
    start_time = args.get("start_time")
    end_time = args.get("end_time")
    entity = args.get("entity", "").strip()
    limit = min(int(args.get("limit", 10)), 50)

    db_path = _get_db_path()
    if not db_path.exists():
        return json.dumps({"result": "Chronos temporal database is empty."})

    init_db()
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        sql = "SELECT id, session_id, event_timestamp, subject, verb, object, event_text, start_time, end_time, entity_aliases FROM chronos_events WHERE 1=1"
        params = []

        if start_time:
            sql += " AND (start_time >= ? OR event_timestamp >= ?)"
            params.extend([start_time, start_time])
        if end_time:
            sql += " AND (end_time <= ? OR event_timestamp <= ?)"
            params.extend([end_time, end_time])
        if entity:
            sql += " AND (entity_aliases LIKE ? OR subject LIKE ? OR object LIKE ?)"
            ent_param = f"%{entity}%"
            params.extend([ent_param, ent_param, ent_param])

        sql += " ORDER BY event_timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()

        events = []
        for row in rows:
            ev_id, ev_session, ev_ts, sub, verb, obj, text, start, end, entities = row
            events.append({
                "event_id": ev_id,
                "session_id": ev_session,
                "event_text": text,
                "subject": sub,
                "verb": verb,
                "object": obj,
                "start_time": start,
                "end_time": end,
                "entities": json.loads(entities or "[]"),
                "timestamp": ev_ts
            })

        return json.dumps({"events": events}, indent=2, ensure_ascii=False)
    finally:
        conn.close()


def check_chronos_requirements() -> bool:
    """Chronos is always available since it uses local SQLite and standard library."""
    return True


# =============================================================================
# OpenAI Function-Calling Schemas
# =============================================================================

CHRONOS_QUERY_SCHEMA = {
    "name": "chronos_query",
    "description": (
        "Query the Chronos temporal memory database (Event Calendar + Turn Calendar) "
        "to find temporally grounded facts, past discussions, or events. "
        "Returns matching events from the Event Calendar and retrieves the corresponding "
        "raw message turns from the Turn Calendar (state.db) as context. "
        "Use this tool when the query is temporally anchored (e.g. 'what did we discuss last Tuesday?', "
        "'when did I mention Vite?')."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords or search phrase to match events (e.g., 'Vite', 'meeting').",
            },
            "start_time": {
                "type": "string",
                "description": "ISO-8601 datetime or date string representing start of search range (e.g. '2026-06-20').",
            },
            "end_time": {
                "type": "string",
                "description": "ISO-8601 datetime or date string representing end of search range (e.g. '2026-06-25').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of events to retrieve (default 5, max 20).",
            }
        },
        "required": [],
    },
}

CHRONOS_LIST_EVENTS_SCHEMA = {
    "name": "chronos_list_events",
    "description": (
        "List events recorded in the Chronos Event Calendar, filtered by temporal range and/or entities."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "start_time": {
                "type": "string",
                "description": "ISO-8601 datetime or date string representing start range.",
            },
            "end_time": {
                "type": "string",
                "description": "ISO-8601 datetime or date string representing end range.",
            },
            "entity": {
                "type": "string",
                "description": "Filter by entity name/alias involved in the event.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of events to return (default 10, max 50).",
            }
        },
        "required": [],
    },
}


# --- Register Tools ---

registry.register(
    name="chronos_query",
    toolset="chronos",
    schema=CHRONOS_QUERY_SCHEMA,
    handler=chronos_query_tool,
    check_fn=check_chronos_requirements,
    emoji="⏰",
)

registry.register(
    name="chronos_list_events",
    toolset="chronos",
    schema=CHRONOS_LIST_EVENTS_SCHEMA,
    handler=chronos_list_events_tool,
    check_fn=check_chronos_requirements,
    emoji="📅",
)
