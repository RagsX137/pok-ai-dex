"""Decide whether a Coach message is asking for a PokemonDB fact, and which one.

Mirrors matchup.py: a pure text -> data-structure utility with no imports from
coach_api or coveo_api, so it can be tested without a server.

The name must resolve EXACTLY against the corpus, for the reason spelled out in
pokemon_names.closest: at edit distance 2 'speed' resolves to 'seel' and 'null'
to 'numel'. A routing decision made on a fuzzy match invents an entity and then
answers confidently about it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class FactIntent:
    pokemon: str   # lowercase canonical name
    topic: str     # one of pokedex.facts.TOPICS


# Ordered: the first pattern to match wins, so the specific ones come first and
# the broad conversational ones come last. "Tell me about Gengar" is a flavour
# question, but "tell me about Gengar's egg groups" is a breeding question, and
# only this ordering gets both right.
_TOPIC_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("abilities", re.compile(r"\b(abilit(?:y|ies)|hidden\s+abilit(?:y|ies))\b", re.I)),
    ("breeding", re.compile(r"\b(breed(?:ing)?|egg\s+group|egg\s+cycle|hatch(?:ing)?)\b", re.I)),
    ("training", re.compile(
        r"\b(ev\s+yield|ev\s+spread|effort\s+values?|catch\s+rate|base\s+exp(?:erience)?"
        r"|growth\s+rate|friendship)\b", re.I)),
    ("evolution", re.compile(r"\b(evolve[sd]?|evolution|evolutionary|evolving)\b", re.I)),
    ("moves", re.compile(
        r"\b(move\s?set|moves?|what\s+does\s+\w+\s+learn|learns?\b)", re.I)),
    ("entries", re.compile(
        r"\b(pok[ée]dex\s+entr(?:y|ies)|flavou?r\s+text|lore|describe|description"
        r"|tell\s+me\s+about|what\s+is\s+\w+\s+like)\b", re.I)),
]

_WORD_SPLIT = re.compile(r"[^A-Za-z0-9'’.:\-]+")


def _corpus_resolve(text: str) -> str | None:
    from pokedex import pokemon_names
    return pokemon_names.resolve(text)


def _candidates(message: str) -> list[str]:
    """Word n-grams from the message, longest first.

    Longest-first matters for two-word names: 'Mr. Mime' must be tried before
    'mime' so the shorter fragment cannot win.

    Each span is offered twice, with and without a trailing dot, because the
    dot is load-bearing in 'Mr. Mime' and 'Mime Jr.' but is just a full stop in
    'Tell me about Mimikyu.'. Stripping it unconditionally loses the first two;
    keeping it unconditionally loses the third.
    """
    words = [w for w in _WORD_SPLIT.split(message or "") if w]
    # Drop possessives, and the punctuation that can never occur inside a name.
    # Dots and colons stay: "Mr.", "Jr.", "Type:".
    cleaned = [re.sub(r"(?:'|’)s$", "", w).strip(",;!?") for w in words]
    cleaned = [w for w in cleaned if w]
    out: list[str] = []
    for n in (3, 2, 1):
        for i in range(len(cleaned) - n + 1):
            span = " ".join(cleaned[i:i + n])
            out.append(span)
            without_dot = span.rstrip(".")
            if without_dot and without_dot != span:
                out.append(without_dot)
    return out


def find_pokemon(message: str) -> str | None:
    """The first exactly-resolving name in the message, preferring longer spans."""
    for candidate in _candidates(message):
        name = _corpus_resolve(candidate)
        if name:
            return name
    return None


def _from_history(history: list[dict] | None) -> str | None:
    """The most recent Pokemon in play, for pronoun questions.

    coach_api tags every stored turn with the canonical names it resolved, so
    "what about its abilities?" can be answered without re-parsing the earlier
    message — and without the misspelling the user may have typed there.
    """
    for turn in reversed(history or []):
        ctx = turn.get("pokemon_context") or []
        if ctx:
            return ctx[0]
    return None


# A question that names no Pokemon and has no pronoun is not about one.
_PRONOUN_RE = re.compile(r"\b(it|its|it's|they|them|their|he|she|his|her)\b", re.I)


def detect_fact_intent(message: str, history: list[dict] | None = None) -> FactIntent | None:
    """Return the FactIntent for `message`, or None to leave it to another path."""
    if not message or not message.strip():
        return None

    topic = next((name for name, pattern in _TOPIC_PATTERNS if pattern.search(message)), None)
    if topic is None:
        return None

    pokemon = find_pokemon(message)
    if pokemon is None and _PRONOUN_RE.search(message):
        pokemon = _from_history(history)
    if pokemon is None:
        return None

    return FactIntent(pokemon=pokemon, topic=topic)
