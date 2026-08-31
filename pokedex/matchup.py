"""
Matchup intent detection.

Decides whether a message is asking "which of my team beats the wild Pokémon"
and if so, resolves the team and wild name from the message + conversation history.

Deliberately has no imports from coach_api or coveo_api — it is a pure utility
that takes text and returns a data structure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Lazily access the shared corpus and resolver to avoid a circular import.
def _corpus() -> frozenset[str]:
    from pokedex import pokemon_names
    return pokemon_names.names()


def _resolve(name: str) -> str | None:
    """Return a canonical lowercase Pokémon name, or None."""
    from pokedex.routes.coveo_api import _closest_pokemon
    return _closest_pokemon(name.lower().strip(), max_dist=2)


# ── team extraction ──────────────────────────────────────────────────────────
# Matches "My team is A, B, C, D, E and F" (6 names, various separators).
_TEAM_RE = re.compile(
    r"(?:my\s+)?team\s+is\s+"
    r"([A-Za-z][A-Za-z\-' ]{1,20})"          # name 1
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 2
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 3
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 4
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 5
    r"(?:,?\s+and\s+([A-Za-z][A-Za-z\-' ]{1,20}))",  # name 6
    re.I,
)

# "which of A, B, C, D, E and F …" or "Out of A, B, C, D, E and F …"
_WHICH_OF_RE = re.compile(
    r"(?:which\s+of|out\s+of)\s+"
    r"([A-Za-z][A-Za-z\-' ]{1,20})"          # name 1
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 2
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 3
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 4
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 5
    r"(?:,?\s+and\s+([A-Za-z][A-Za-z\-' ]{1,20}))",  # name 6
    re.I,
)

# ── probe classification ─────────────────────────────────────────────────────
_AVOID_RE = re.compile(r"\b(avoid|bad idea|bad choice|worst|not send|shouldn't send|should not send)\b", re.I)
_RANKING_RE = re.compile(r"\b(safest|best|single|single one|top pick|who should i lead|lead with)\b", re.I)

# ── wild extraction ──────────────────────────────────────────────────────────
_AGAINST_RE = re.compile(
    r"\b(?:against|vs\.?|versus|fight(?:ing)?|face|encounter(?:ing)?)\s+"
    r"([A-Za-z][A-Za-z\-']{2,24})\b",
    re.I,
)


@dataclass
class MatchupIntent:
    team: list[str]   # lowercase canonical names
    wild: str         # lowercase canonical name
    probe: str        # "advantage" | "avoid" | "ranking"


def _extract_team(text: str) -> list[str] | None:
    """Return a list of up to 6 resolved names, or None if fewer than 2 resolve."""
    for pattern in (_TEAM_RE, _WHICH_OF_RE):
        m = pattern.search(text)
        if m:
            raw = [g for g in m.groups() if g]
            resolved = [r for r in (_resolve(n) for n in raw) if r]
            if len(resolved) >= 2:
                return resolved
    return None


def _extract_wild_from_text(text: str) -> str | None:
    for m in _AGAINST_RE.finditer(text):
        r = _resolve(m.group(1))
        if r:
            return r
    return None


def _extract_wild_from_history(history: list[dict]) -> str | None:
    """Walk backwards through history looking for pokemon_context on Oak turns."""
    for turn in reversed(history):
        ctx = turn.get("pokemon_context") or []
        if ctx:
            # The first entry in context for assistant turns is typically the
            # wild Pokémon (it's the one being described).
            r = _resolve(ctx[0])
            if r:
                return r
    return None


def _classify_probe(text: str) -> str:
    low = text.lower()
    if _AVOID_RE.search(low):
        return "avoid"
    if _RANKING_RE.search(low):
        return "ranking"
    return "advantage"


# ── public API ───────────────────────────────────────────────────────────────

def detect_matchup_intent(message: str, history: list[dict]) -> MatchupIntent | None:
    """
    Return a MatchupIntent if the message is asking which teammate beats a wild
    Pokémon, else None.

    Requires:
      - A resolvable team of at least 2 Pokémon (either stated in the message
        or in the "which of X, Y, Z…" pattern).
      - A resolvable wild Pokémon (from "against X" in the message, or from
        the last pokemon_context entry in conversation history).
    """
    if not _corpus():
        return None  # name corpus not loaded; fall through to LLM path

    team = _extract_team(message)
    if not team:
        return None

    wild = _extract_wild_from_text(message) or _extract_wild_from_history(history)
    if not wild:
        return None

    # Exclude the wild from the team in case of accidental overlap.
    team = [t for t in team if t != wild]
    if not team:
        return None

    probe = _classify_probe(message)
    return MatchupIntent(team=team, wild=wild, probe=probe)
