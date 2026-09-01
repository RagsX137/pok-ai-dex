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
_URLS: dict[str, str] = {}
_LOADED = False


def init(repo_root: Path) -> None:
    """Load the corpus. Never raises: a missing CSV degrades to 'nothing
    resolves', which is the safe direction."""
    global _NAMES, _URLS, _LOADED
    try:
        path = Path(repo_root) / "data" / "pokemon_db.csv"
        with path.open(newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("pokemon")]
        _NAMES = frozenset(r["pokemon"].strip().lower() for r in rows)
        _URLS = {
            r["pokemon"].strip().lower(): (r.get("url") or "").strip()
            for r in rows if (r.get("url") or "").strip()
        }
    except Exception:
        _NAMES = frozenset()
        _URLS = {}
    _LOADED = True


def _ensure_loaded() -> None:
    """Populate the corpus on first use.

    This used to be a module-scope init() in coveo_api.py, which made every
    other consumer's correctness depend on that one module being imported
    first: `import pokedex.matchup` on its own left the corpus empty, and an
    empty corpus resolves nothing, so matchup routing silently disabled
    itself instead of failing. Loading on demand removes the ordering
    dependency; create_app() still calls init() explicitly so the server pays
    the cost at startup rather than on the first request.
    """
    if not _LOADED:
        from pokedex.config import settings  # local: config must not import us
        init(settings.repo_root)


def names() -> frozenset[str]:
    _ensure_loaded()
    return _NAMES


def url_for(name: str) -> str | None:
    """The pokemondb.net page URL for a name, or None.

    Read from the same CSV row as the name itself, so there is no second
    corpus to drift. Coach cites facts with it: the Passage Retrieval API
    returns a document title and id but no clickable URL.
    """
    _ensure_loaded()
    return _URLS.get(_norm(name))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def resolve(text: str, universe: frozenset[str] | None = None) -> str | None:
    """Exact match after normalisation. No fuzzing, no coercion."""
    _ensure_loaded()
    pool = _NAMES if universe is None else universe
    key = _norm(text)
    return key if key in pool else None


# Punctuation that the NAME_CHARS character class admits but that legitimately
# trails a Pokémon name when it ends a sentence or clause, e.g. "Blaziken."
# or "Farfetch'd,".  Only stripped as a fallback: the dotted form is tried
# first so "mime jr." (where the period is part of the canonical name) still
# resolves correctly.
_TRAILING_PUNCT = re.compile(r"[.,!?;:\"\)]+$")
_LEADING_PUNCT  = re.compile(r"^[\"(\[]+")


def _strip_punct(word: str) -> str:
    return _LEADING_PUNCT.sub("", _TRAILING_PUNCT.sub("", word))


def resolve_suffix(text: str, universe=None, max_words: int = 3) -> str | None:
    """Longest trailing word-run that is a real name.

    'should i use charizard' -> 'charizard'. Trailing, because English puts the
    lead-in before the name.

    Each candidate is tried as-is first, then with trailing punctuation stripped
    from the last word.  This means "charizard." falls back to "charizard" while
    "mime jr." (period is canonical) still resolves on the first attempt.
    """
    _ensure_loaded()
    pool = _NAMES if universe is None else universe
    words = _norm(text).split(" ")
    for n in range(min(max_words, len(words)), 0, -1):
        cand = " ".join(words[-n:])
        if cand in pool:
            return cand
        # Fallback: strip trailing punctuation from the last word only.
        stripped_last = _strip_punct(words[-1])
        if stripped_last != words[-1]:
            fallback = " ".join(words[-n:-1] + [stripped_last]) if n > 1 else stripped_last
            if fallback in pool:
                return fallback
    return None


def resolve_prefix(text: str, universe=None, max_words: int = 3) -> str | None:
    """Longest leading word-run that is a real name.

    'blastoise against this' -> 'blastoise'. Leading, because trailing junk is
    what a greedy second capture group picks up.

    Each candidate is tried as-is first, then with trailing punctuation stripped
    from the last word.  This means "blaziken." falls back to "blaziken" while
    "mime jr." (period is canonical) still resolves on the first attempt.
    """
    _ensure_loaded()
    pool = _NAMES if universe is None else universe
    words = _norm(text).split(" ")
    for n in range(min(max_words, len(words)), 0, -1):
        cand = " ".join(words[:n])
        if cand in pool:
            return cand
        # Fallback: strip trailing punctuation from the last word only.
        stripped_last = _strip_punct(words[n - 1])
        if stripped_last != words[n - 1]:
            fallback = " ".join(words[:n - 1] + [stripped_last]) if n > 1 else stripped_last
            if fallback in pool:
                return fallback
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
    _ensure_loaded()
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
