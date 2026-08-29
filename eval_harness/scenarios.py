"""
Scenario generation: a random team of six, a wild encounter that is not on it,
and the questions to ask about the matchup.

Draws are seeded, so any run is reproducible from its run_id + seed. Axes let
you *guarantee* coverage of the interesting cases (an immunity trap, a matchup
where no teammate has any advantage) instead of hoping a random draw hits one.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

TEAM_SIZE = 6


@dataclass
class Scenario:
    axis: str
    wild: str
    team: list[str]
    ground_truth: dict
    probes: list[tuple[str, str]] = field(default_factory=list)


# ── axis predicates ──────────────────────────────────────────────────────────
def _mus(gt):
    return list(gt["matchups"].values())


AXES: dict[str, tuple[str, callable]] = {
    "any": (
        "No constraint - a plain random draw",
        lambda gt: True,
    ),
    "baseline": (
        "Single-type wild with at least one clean counter on the team",
        lambda gt: len(gt["wild_types"]) == 1 and bool(gt["advantage"]),
    ),
    "dual_type": (
        "Dual-type wild - the second type can cancel an apparent advantage",
        lambda gt: len(gt["wild_types"]) == 2 and bool(gt["advantage"]),
    ),
    "four_x_defence": (
        "A teammate takes 4x - the single worst pick, easy to recommend by mistake",
        lambda gt: any(m["worst_taken"] >= 4 for m in _mus(gt)),
    ),
    "four_x_offence": (
        "A teammate hits for 4x - the most useful fact available",
        lambda gt: any(m["best_stab"] >= 4 for m in _mus(gt)),
    ),
    "zero_damage": (
        "A teammate has a STAB type that deals 0x - it cannot land that hit at all",
        lambda gt: any(m["dead_types"] for m in _mus(gt)),
    ),
    "no_advantage": (
        "Nobody on the team has an advantage - the honest answer is 'none'",
        lambda gt: gt["no_advantage_exists"],
    ),
    "immune_wall": (
        "A teammate is immune to the wild Pokemon's STAB - the safest possible switch-in",
        lambda gt: any(m["immune_to_wild"] for m in _mus(gt)),
    ),
}

# The default battery: one scenario per axis, covering every failure mode the
# manual eval surfaced.
DEFAULT_AXES = [
    "baseline",
    "dual_type",
    "four_x_defence",
    "zero_damage",
    "no_advantage",
]


# ── question templates ───────────────────────────────────────────────────────
def _listing(team: list[str]) -> str:
    return ", ".join(team[:-1]) + " and " + team[-1]


PROBES: dict[str, tuple[str, callable]] = {
    "lookup": (
        "Baseline retrieval - does it know this Pokemon at all?",
        lambda w, t: f"Tell me about {w}",
    ),
    "advantage": (
        "Core task - which teammate has a type advantage",
        lambda w, t: (
            f"My team is {_listing(t)}. "
            f"Which of these has a type advantage against {w}?"
        ),
    ),
    "avoid": (
        "Defensive reasoning - which teammate is a bad idea",
        lambda w, t: (
            f"Which of {_listing(t)} would be a bad idea to send out against {w}, and why?"
        ),
    ),
    "pronoun": (
        "Conversational memory - the wild Pokemon is only 'it'",
        lambda w, t: f"My team is {_listing(t)}. Which of them can beat it?",
    ),
    "unnamed_team": (
        "Harder memory probe - neither the team nor the wild Pokemon is restated",
        lambda w, t: "Which of my team should I send out against it?",
    ),
    "ranking": (
        "Ranking - forces a single best answer with a reason",
        lambda w, t: (
            f"Out of {_listing(t)}, which single one is the safest switch-in "
            f"against {w} and why?"
        ),
    ),
}

DEFAULT_PROBES = ["lookup", "advantage", "avoid", "pronoun", "ranking"]


class ScenarioBuilder:
    def __init__(self, pool: list[str], chart, rng: random.Random):
        self.pool = pool
        self.chart = chart
        self.rng = rng
        self._unresolvable: set[str] = set()

    def draw(self, axis: str = "any", max_attempts: int = 400) -> Scenario | None:
        """Rejection-sample a team + wild pair satisfying `axis`."""
        if axis not in AXES:
            raise ValueError(f"unknown axis {axis!r}; choose from {sorted(AXES)}")
        predicate = AXES[axis][1]
        candidates = [n for n in self.pool if n not in self._unresolvable]

        for _ in range(max_attempts):
            if len(candidates) < TEAM_SIZE + 1:
                return None
            picks = self.rng.sample(candidates, TEAM_SIZE + 1)
            team, wild = picks[:TEAM_SIZE], picks[TEAM_SIZE]
            try:
                gt = self.chart.ground_truth(team, wild)
            except Exception:
                # One of the seven has no PokeAPI entry (regional form, odd
                # punctuation). Drop them from the pool and redraw.
                for n in picks:
                    if not self.chart.known(n):
                        self._unresolvable.add(n)
                candidates = [n for n in candidates if n not in self._unresolvable]
                continue
            if predicate(gt):
                return Scenario(axis=axis, wild=wild, team=team, ground_truth=gt)
        return None

    @staticmethod
    def attach_probes(sc: Scenario, probes: list[str]) -> Scenario:
        sc.probes = [(p, PROBES[p][1](sc.wild, sc.team)) for p in probes]
        return sc

    def battery(
        self, axes: list[str] | None = None, probes: list[str] | None = None
    ) -> list[Scenario]:
        axes = axes or DEFAULT_AXES
        probes = probes or DEFAULT_PROBES
        out = []
        for axis in axes:
            sc = self.draw(axis)
            if sc is None:
                continue
            out.append(self.attach_probes(sc, probes))
        return out
