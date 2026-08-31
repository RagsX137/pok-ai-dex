"""
The pool of Pokemon the harness draws teams from.

Names are harvested from the *live Coveo index* rather than a static list, so
scenarios can only ever use Pokemon the app could actually retrieve. Cached to
disk; refresh with `--refresh-corpus`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

# pokemondb.net page titles look like:
#   "Tyrantrum Pokedex: stats, moves, evolution & locations | Pokemon Database"
TITLE_RE = re.compile(r"^(.+?)\s+Pok[eé]dex:\s*stats,\s*moves,\s*evolution", re.I)

# Broad queries used to sweep the index. Coveo caps a single request's window,
# so we paginate each of these and union the results.
SWEEP_QUERIES = [
    "pokedex stats moves evolution",
    "pokemon",
    "type",
    "evolution",
    "abilities base stats",
]


class Corpus:
    def __init__(self, client, cache_path: Path):
        self.client = client
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self, refresh: bool = False, page_size: int = 100, depth: int = 400) -> list[str]:
        if self.cache_path.exists() and not refresh:
            return json.loads(self.cache_path.read_text())
        names = self.harvest(page_size=page_size, depth=depth)
        self.cache_path.write_text(json.dumps(names, indent=0))
        return names

    def harvest(self, page_size: int = 100, depth: int = 400) -> list[str]:
        found: set[str] = set()
        for q in SWEEP_QUERIES:
            for first in range(0, depth, page_size):
                try:
                    results = self.client.search(q, num=page_size, first=first)
                except requests.RequestException:
                    continue
                if not results:
                    break
                for r in results:
                    m = TITLE_RE.match(r.get("title", ""))
                    if m:
                        found.add(m.group(1).strip())
        return sorted(found)
