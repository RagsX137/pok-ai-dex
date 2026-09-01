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
    """Return a canonical lowercase Pokémon name, or None.
    Exact resolution only — routing decisions must never invent an entity.
    """
    from pokedex import pokemon_names
    return pokemon_names.resolve(name.lower().strip())


# ── team extraction ──────────────────────────────────────────────────────────
# The lead-in, then one greedy span of "things a name list is made of".
#
# These used to be six mandatory capture groups, so ONLY an exactly-six-name
# team matched and every real trainer with three or four Pokémon fell through
# to the LLM — the deterministic path was reachable almost exclusively by the
# eval harness's own phrasing. The span is split and resolved instead, which
# makes the arity free: the list ends where the names stop resolving.
_LIST_SPAN = r"([A-Za-z][A-Za-z0-9'’.\-: ,]{1,200})"
_TEAM_RE = re.compile(r"(?:my\s+)?team\s+is\s+" + _LIST_SPAN, re.I)
_WHICH_OF_RE = re.compile(r"(?:which\s+of|out\s+of)\s+" + _LIST_SPAN, re.I)

# Splits the span on the separators a spoken list uses. A name never contains
# a comma or the standalone word "and".
_LIST_SEP = re.compile(r",|\band\b", re.I)

_MAX_TEAM = 6

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


def _names_in_span(span: str) -> list[str]:
    """Resolve a comma/and-separated span into the names it opens with.

    Two rules end the list, both needed because the span runs past the end of
    the sentence (a period is legal inside "Mr. Mime", so it cannot terminate
    the capture):

      1. A piece that resolves to nothing — "which single one is the safest
         switch-in against Raichu" — ends it.
      2. A piece with trailing prose after the name it starts with —
         "Gothita. Which of them has an advantage" — is the last entry. Names
         in a following sentence are not team members.
    """
    from pokedex import pokemon_names

    out: list[str] = []
    for piece in _LIST_SEP.split(span):
        piece = piece.strip(" \t.,")
        if not piece:
            continue
        name = pokemon_names.resolve_prefix(piece, max_words=3)
        if not name:
            break
        if name not in out:
            out.append(name)
        # The name did not use up the whole piece: prose has begun.
        if len(piece.split(" ")) > len(name.split(" ")):
            break
        if len(out) >= _MAX_TEAM:
            break
    return out


def _extract_team(text: str) -> list[str] | None:
    """Return the 2–6 resolved names the message lists, or None."""
    for pattern in (_TEAM_RE, _WHICH_OF_RE):
        m = pattern.search(text)
        if m:
            resolved = _names_in_span(m.group(1))
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
