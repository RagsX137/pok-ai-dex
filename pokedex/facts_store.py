"""Resolve a Pokemon's facts from a file, a cache, or the Passage Retrieval API.

Three tiers, cheapest first:

  1. data/pokemon_facts.json, if it has been built (scripts/ingest/build_facts.py)
  2. an in-process LRU, so repeat questions in a session cost nothing
  3. one live passage call, parsed and then cached

The file is optional in exactly the way eval_data/*.json is for coach_api's
grader: absent, the store still works and just pays for the first question
about each Pokemon.
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from pathlib import Path

from pokedex.config import settings as default_settings
from pokedex.coveo import CoveoClient
from pokedex.facts import PokemonFacts, build_facts, fold

# Chunks are 11-15 KB each and several belong to the same document, so a
# generous ceiling here is what makes full section coverage likely. Measured
# 8/8 on a name-only query at this value; see the plan doc.
_MAX_PASSAGES = 10

_CACHE_CAPACITY = 512


class FactsStore:
    """Thread-safe, bounded cache over the three tiers above.

    Never raises: every failure path returns None, which coach_api turns into a
    fall-through to CRGA. A Pokemon we cannot describe is a worse answer, not a
    broken request.
    """

    def __init__(
        self,
        client: CoveoClient | None = None,
        path: Path | None = None,
        capacity: int = _CACHE_CAPACITY,
    ):
        self._client = client
        self._capacity = capacity
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, PokemonFacts] = OrderedDict()
        self._file: dict[str, dict] = {}

        facts_path = path if path is not None else (default_settings.repo_root
                                                    / "data" / "pokemon_facts.json")
        try:
            if facts_path and Path(facts_path).exists():
                raw = json.loads(Path(facts_path).read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._file = {fold(k): v for k, v in raw.items()}
        except Exception:
            # A corrupt or half-written facts file must not stop the server from
            # booting; the live path covers it.
            self._file = {}

    # ── internals ────────────────────────────────────────────────────────────

    def _cached(self, key: str) -> PokemonFacts | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def _store(self, key: str, facts: PokemonFacts) -> None:
        with self._lock:
            self._cache[key] = facts
            self._cache.move_to_end(key)
            while len(self._cache) > self._capacity:
                self._cache.popitem(last=False)

    def _fetch(self, name: str) -> PokemonFacts | None:
        """One live passage call, filtered to this Pokemon's own document."""
        client = self._client or CoveoClient()
        # clean=False: the parser needs the headings and short table cells that
        # clean_passage_text exists to remove. See coveo.retrieve_passages.
        passages = client.retrieve_passages(name, max_passages=_MAX_PASSAGES, clean=False)
        if not passages:
            return None

        # Retrieval is query-driven, so a query for "Bulbasaur" also returns
        # Ivysaur and Venusaur. Titles read "Bulbasaur Pokédex: stats, moves,
        # ..." — match on the leading name, folded, or Pokédex's accent makes
        # every comparison fail.
        prefix = fold(name) + " "
        mine = [p.text for p in passages if fold(p.title).startswith(prefix)]
        if not mine:
            return None
        return build_facts(name, mine)

    # ── public ───────────────────────────────────────────────────────────────

    def get(self, name: str) -> PokemonFacts | None:
        if not name or not name.strip():
            return None
        key = fold(name.strip())

        hit = self._cached(key)
        if hit is not None:
            return hit

        from_file = self._file.get(key)
        if from_file is not None:
            try:
                facts = PokemonFacts.from_dict(from_file)
                self._store(key, facts)
                return facts
            except Exception:
                pass  # fall through to the live path

        try:
            facts = self._fetch(key)
        except Exception:
            return None
        if facts is None:
            return None
        self._store(key, facts)
        return facts
