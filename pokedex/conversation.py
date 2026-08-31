"""In-memory conversation session store.

Sessions are keyed by session_id (UUID string from the client).
Each session holds at most MAX_TURNS turns; oldest are evicted when the
limit is exceeded. Sessions themselves are bounded to MAX_SESSIONS using
LRU eviction so the process cannot grow unboundedly.
No persistence — sessions are lost on server restart.
"""
from __future__ import annotations

from collections import OrderedDict, deque

MAX_TURNS: int = 20
MAX_SESSIONS: int = 1_000

# OrderedDict for LRU eviction: { session_id: deque of {role, content, pokemon_context} }
_sessions: OrderedDict[str, deque[dict]] = OrderedDict()


def _touch(session_id: str) -> None:
    """Mark session as recently used (move to end of OrderedDict)."""
    _sessions.move_to_end(session_id)


def get_or_create(session_id: str) -> list[dict]:
    """Return the current turn list for a session (creates empty if new)."""
    if session_id not in _sessions:
        if len(_sessions) >= MAX_SESSIONS:
            _sessions.popitem(last=False)  # evict least-recently-used
        _sessions[session_id] = deque(maxlen=MAX_TURNS)
    else:
        _touch(session_id)
    return list(_sessions[session_id])


def append_turn(
    session_id: str,
    role: str,
    content: str,
    pokemon_context: list[str] | None = None,
) -> None:
    """Append a turn; oldest turn is dropped automatically when MAX_TURNS is hit."""
    if session_id not in _sessions:
        if len(_sessions) >= MAX_SESSIONS:
            _sessions.popitem(last=False)
        _sessions[session_id] = deque(maxlen=MAX_TURNS)
    else:
        _touch(session_id)
    _sessions[session_id].append(
        {"role": role, "content": content, "pokemon_context": pokemon_context}
    )


def get_history(session_id: str) -> list[dict]:
    """Return a copy of the session's turn list; empty list if unknown."""
    session = _sessions.get(session_id)
    if session is not None:
        _touch(session_id)
    return list(session) if session is not None else []


def clear(session_id: str) -> None:
    """Remove all turns for the session."""
    _sessions.pop(session_id, None)
