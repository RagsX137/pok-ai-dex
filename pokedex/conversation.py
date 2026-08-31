"""In-memory conversation session store.

Sessions are keyed by session_id (UUID string from the client).
Each session holds at most MAX_TURNS turns; oldest are evicted when the
limit is exceeded. No persistence — sessions are lost on server restart.
"""
from __future__ import annotations

from collections import deque
from typing import Deque

MAX_TURNS: int = 20

# { session_id: deque of {role, content, pokemon_context} }
_sessions: dict[str, Deque[dict]] = {}


def get_or_create(session_id: str) -> list[dict]:
    """Return the current turn list for a session (creates empty if new)."""
    if session_id not in _sessions:
        _sessions[session_id] = deque(maxlen=MAX_TURNS)
    return list(_sessions[session_id])


def append_turn(
    session_id: str,
    role: str,
    content: str,
    pokemon_context: list[str] | None = None,
) -> None:
    """Append a turn; oldest turn is dropped automatically when MAX_TURNS is hit."""
    if session_id not in _sessions:
        _sessions[session_id] = deque(maxlen=MAX_TURNS)
    _sessions[session_id].append(
        {"role": role, "content": content, "pokemon_context": pokemon_context}
    )


def get_history(session_id: str) -> list[dict]:
    """Return a copy of the session's turn list; empty list if unknown."""
    return list(_sessions.get(session_id, []))


def clear(session_id: str) -> None:
    """Remove all turns for the session."""
    _sessions.pop(session_id, None)
