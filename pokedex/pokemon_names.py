"""
One source of truth for "is this string a Pokemon name?".

Four call sites used to answer this question with four different ad-hoc
character classes over two different corpora, which is why Porygon-Z, Ho-Oh and
Type: Null were each recognised by some of them and none of the others.

`resolve` is exact: routing and grading decisions must never invent an entity.
`closest` is the fuzzy edit-distance matcher, and exists only for the
user-facing /api/pokemon-correct spell-check endpoint, where a wrong guess is
visible to the user and harmless.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

# Every character that occurs in a real name: Porygon-Z, Porygon2, Farfetch'd,
# Mr. Mime, Type: Null, Ho-Oh, Mime Jr.
NAME_CHARS = r"A-Za-z0-9''.\-: "

_NAMES: frozenset[str] = frozenset()


def init(repo_root: Path) -> None:
    """Load the corpus once at import time. Never raises: a missing CSV
    degrades to 'nothing resolves', which is the safe direction."""
    global _NAMES
    try:
        path = Path(repo_root) / "data" / "pokemon_db.csv"
        with path.open(newline="", encoding="utf-8") as f:
            _NAMES = frozenset(
                r["pokemon"].strip().lower()
                for r in csv.DictReader(f) if r.get("pokemon")
            )
    except Exception:
        _NAMES = frozenset()


def names() -> frozenset[str]:
    return _NAMES


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def resolve(text: str, universe: frozenset[str] | None = None) -> str | None:
    """Exact match after normalisation. No fuzzing, no coercion."""
    pool = _NAMES if universe is None else universe
    key = _norm(text)
    return key if key in pool else None


def resolve_suffix(text: str, universe=None, max_words: int = 3) -> str | None:
    """Longest trailing word-run that is a real name.

    'should i use charizard' -> 'charizard'. Trailing, because English puts the
    lead-in before the name.
    """
    pool = _NAMES if universe is None else universe
    words = _norm(text).split(" ")
    for n in range(min(max_words, len(words)), 0, -1):
        cand = " ".join(words[-n:])
        if cand in pool:
            return cand
    return None


def resolve_prefix(text: str, universe=None, max_words: int = 3) -> str | None:
    """Longest leading word-run that is a real name.

    'blastoise against this' -> 'blastoise'. Leading, because trailing junk is
    what a greedy second capture group picks up.
    """
    pool = _NAMES if universe is None else universe
    words = _norm(text).split(" ")
    for n in range(min(max_words, len(words)), 0, -1):
        cand = " ".join(words[:n])
        if cand in pool:
            return cand
    return None


def _edit_distance(a: str, b: str) -> int:
    """Standard DP Levenshtein distance."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = curr
    return prev[-1]


def closest(name: str, max_dist: int = 2) -> str | None:
    """Fuzzy match — SPELL-CHECK ONLY.

    Do not use this to make a routing or grading decision. At max_dist=2 it maps
    'speed'->'seel', 'tank'->'sawk', 'null'->'numel'. It is correct only where a
    wrong guess is shown to the user for confirmation.
    """
    if not _NAMES or not name:
        return None
    key = _norm(name)
    if key in _NAMES:
        return key
    best_name, best_dist = None, max_dist + 1
    for candidate in _NAMES:
        d = _edit_distance(key, candidate)
        if d < best_dist:
            best_dist, best_name = d, candidate
    return best_name if best_dist <= max_dist else None
