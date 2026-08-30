"""
Type-effectiveness ground truth.

The 18x18 chart is embedded (generated from PokeAPI type damage relations) so
grading is deterministic and works offline. Per-Pokemon typings still come from
PokeAPI, cached to disk on first fetch.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

TYPES = [
    "normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost",
    "steel", "fire", "water", "grass", "electric", "psychic", "ice", "dragon",
    "dark", "fairy",
]

# attacker -> (double_damage_to, half_damage_to, no_damage_to)
_RELATIONS: dict[str, tuple[list[str], list[str], list[str]]] = {
    "normal": ([], ['rock', 'steel'], ['ghost']),
    "fighting": (['normal', 'rock', 'steel', 'ice', 'dark'], ['flying', 'poison', 'bug', 'psychic', 'fairy'], ['ghost']),
    "flying": (['fighting', 'bug', 'grass'], ['rock', 'steel', 'electric'], []),
    "poison": (['grass', 'fairy'], ['poison', 'ground', 'rock', 'ghost'], ['steel']),
    "ground": (['poison', 'rock', 'steel', 'fire', 'electric'], ['bug', 'grass'], ['flying']),
    "rock": (['flying', 'bug', 'fire', 'ice'], ['fighting', 'ground', 'steel'], []),
    "bug": (['grass', 'psychic', 'dark'], ['fighting', 'flying', 'poison', 'ghost', 'steel', 'fire', 'fairy'], []),
    "ghost": (['ghost', 'psychic'], ['dark'], ['normal']),
    "steel": (['rock', 'ice', 'fairy'], ['steel', 'fire', 'water', 'electric'], []),
    "fire": (['bug', 'steel', 'grass', 'ice'], ['rock', 'fire', 'water', 'dragon'], []),
    "water": (['ground', 'rock', 'fire'], ['water', 'grass', 'dragon'], []),
    "grass": (['ground', 'rock', 'water'], ['flying', 'poison', 'bug', 'steel', 'fire', 'grass', 'dragon'], []),
    "electric": (['flying', 'water'], ['grass', 'electric', 'dragon'], ['ground']),
    "psychic": (['fighting', 'poison'], ['steel', 'psychic'], ['dark']),
    "ice": (['flying', 'ground', 'grass', 'dragon'], ['steel', 'fire', 'water', 'ice'], []),
    "dragon": (['dragon'], ['steel'], ['fairy']),
    "dark": (['ghost', 'psychic'], ['fighting', 'dark', 'fairy'], []),
    "fairy": (['fighting', 'dragon', 'dark'], ['poison', 'steel', 'fire'], []),
}

CHART: dict[str, dict[str, float]] = {
    a: {d: 1.0 for d in TYPES} for a in TYPES
}
for _att, (_dbl, _half, _none) in _RELATIONS.items():
    for _d in _dbl:
        CHART[_att][_d] = 2.0
    for _d in _half:
        CHART[_att][_d] = 0.5
    for _d in _none:
        CHART[_att][_d] = 0.0


class TypeChart:
    """Pokemon typings (cached from PokeAPI) plus effectiveness maths."""

    API = "https://pokeapi.co/api/v2"

    def __init__(self, cache_path: Path, offline: bool = False):
        self.cache_path = Path(cache_path)
        self.offline = offline
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if self.cache_path.exists():
            self._types: dict[str, list[str]] = json.loads(self.cache_path.read_text())
        else:
            self._types = {}

    # ── typings ──────────────────────────────────────────────────────────────
    @staticmethod
    def slug(name: str) -> str:
        s = name.lower().strip()
        s = s.replace("\u2640", "-f").replace("\u2642", "-m")
        s = re.sub(r"[.'\u2019:]", "", s)
        s = re.sub(r"[\s_]+", "-", s)
        return s

    def types_of(self, name: str) -> list[str]:
        """Types for `name`, e.g. ['rock', 'dragon']. Raises if unresolvable."""
        key = self.slug(name)
        if key in self._types:
            return self._types[key]
        if self.offline:
            raise LookupError(f"{name!r} not in type cache and offline=True")
        r = requests.get(f"{self.API}/pokemon/{key}", timeout=30)
        r.raise_for_status()
        types = [t["type"]["name"] for t in r.json()["types"]]
        self._types[key] = types
        self._flush()
        return types

    def known(self, name: str) -> bool:
        try:
            self.types_of(name)
            return True
        except Exception:
            return False

    def _flush(self) -> None:
        self.cache_path.write_text(json.dumps(self._types, indent=0, sort_keys=True))

    # ── effectiveness ────────────────────────────────────────────────────────
    @staticmethod
    def effectiveness(attack_type: str, defender_types: list[str]) -> float:
        m = 1.0
        for d in defender_types:
            m *= CHART[attack_type][d]
        return m

    def matchup(self, member: str, wild: str) -> dict:
        """
        How `member` fares against `wild`, using same-type-attack-bonus types as
        a proxy for the moves a Pokemon actually brings.
        """
        mt = self.types_of(member)
        wt = self.types_of(wild)
        offence = {t: self.effectiveness(t, wt) for t in mt}
        defence = {t: self.effectiveness(t, mt) for t in wt}
        best = max(offence.values())
        worst = max(defence.values())
        return {
            "member": member,
            "member_types": mt,
            "wild_types": wt,
            # STAB types that deal literally zero damage (e.g. Ground into Flying).
            # A recommendation built on one of these can never land.
            "dead_types": [t for t, v in offence.items() if v == 0.0],
            "offence": offence,
            "defence": defence,
            "best_stab": best,
            "worst_taken": worst,
            "has_advantage": best >= 2.0,
            "cannot_hit": best == 0.0,
            "is_liability": worst >= 2.0 or best <= 0.5,
            "immune_to_wild": worst == 0.0,
        }

    def ground_truth(self, team: list[str], wild: str) -> dict:
        """Full expected answer for a scenario - what a correct Pokedex would say."""
        ms = [self.matchup(m, wild) for m in team]
        advantage = [m["member"] for m in ms if m["has_advantage"]]
        liabilities = [m["member"] for m in ms if m["is_liability"]]
        cannot_hit = [m["member"] for m in ms if m["cannot_hit"]]

        def rank_key(m):
            return (-m["best_stab"], m["worst_taken"])

        ranked = sorted(ms, key=rank_key)
        return {
            "wild": wild,
            "wild_types": self.types_of(wild),
            "matchups": {m["member"]: m for m in ms},
            "advantage": advantage,
            "liabilities": liabilities,
            "cannot_hit": cannot_hit,
            "best_pick": ranked[0]["member"] if ranked and ranked[0]["best_stab"] >= 2 else None,
            "no_advantage_exists": not advantage,
        }
