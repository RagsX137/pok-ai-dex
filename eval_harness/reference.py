"""
Renders the ideal answer for a scenario straight from the type chart.

This is the answer the Pokedex *should* have given. It is used three ways:
as the target in exported training pairs, as the corrective half of a few-shot
prompt example, and as a worked reference when reviewing a run by hand.
"""
from __future__ import annotations


def _mult(m: float) -> str:
    return f"{m:g}x"


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _best_type(mu: dict) -> tuple[str, float]:
    t = max(mu["offence"], key=mu["offence"].get)
    return t, mu["offence"][t]


def ideal_answer(probe: str, gt: dict, team: list[str]) -> str:
    wild = gt["wild"]
    wt = "/".join(t.capitalize() for t in gt["wild_types"])
    mus = gt["matchups"]

    if probe == "lookup":
        return f"{wild} is a {wt} type Pokemon."

    if probe == "avoid":
        bad = []
        for name in gt["liabilities"]:
            mu = mus[name]
            why = []
            if mu["dead_types"]:
                why.append(
                    f"its {'/'.join(t.capitalize() for t in mu['dead_types'])} attacks "
                    f"deal no damage at all"
                )
            if mu["worst_taken"] >= 2:
                why.append(f"it takes {_mult(mu['worst_taken'])} damage")
            if mu["best_stab"] <= 0.5:
                why.append(f"it can only hit for {_mult(mu['best_stab'])}")
            bad.append(f"{name} ({'; '.join(why)})")
        if not bad:
            return (
                f"None of {_join(team)} is at a particular disadvantage against "
                f"{wild} ({wt}) - no one on the team takes extra damage from its attacks."
            )
        return f"Against {wild} ({wt}), avoid " + _join(bad) + "."

    # advantage / pronoun / ranking / unnamed_team
    if gt["no_advantage_exists"]:
        neutral = [n for n in team if mus[n]["best_stab"] >= 1 and not mus[n]["is_liability"]]
        out = (
            f"None of {_join(team)} has a type advantage against {wild} ({wt}). "
            f"{wild} is only weak to "
            + _join(sorted(_weaknesses(gt))) + ", which nobody on this team brings."
        )
        if neutral:
            out += f" The safest neutral options are {_join(neutral)}."
        if gt["liabilities"]:
            out += f" Avoid {_join(gt['liabilities'])}."
        return out

    parts = []
    for name in sorted(gt["advantage"], key=lambda n: -mus[n]["best_stab"]):
        t, m = _best_type(mus[name])
        note = ""
        if mus[name]["immune_to_wild"]:
            note = f", and is immune to {wild}'s {'/'.join(gt['wild_types']).capitalize()} attacks"
        elif mus[name]["worst_taken"] >= 2:
            note = f", though it takes {_mult(mus[name]['worst_taken'])} back"
        parts.append(f"{name} ({t.capitalize()}, {_mult(m)}{note})")

    lead = (
        f"Against {wild} ({wt}), "
        + _join(parts)
        + f" {'has' if len(parts) == 1 else 'have'} a type advantage."
    )
    if probe == "ranking":
        best = _safest(gt)
        mu = mus[best]
        t, m = _best_type(mu)
        lead = (
            f"The safest switch-in against {wild} ({wt}) is {best}: it hits for "
            f"{_mult(m)} with {t.capitalize()}"
            + (
                f" and takes no damage from {wild}'s attacks."
                if mu["immune_to_wild"]
                else f" and takes only {_mult(mu['worst_taken'])} back."
            )
        )
    if gt["liabilities"]:
        lead += f" Do not send {_join(gt['liabilities'])}."
    return lead


def _weaknesses(gt: dict) -> list[str]:
    from .typechart import CHART, TYPES
    out = []
    for att in TYPES:
        m = 1.0
        for d in gt["wild_types"]:
            m *= CHART[att][d]
        if m >= 2:
            out.append(f"{att.capitalize()} ({_mult(m)})")
    return out


def _safest(gt: dict) -> str:
    """Best offence, immunity as tie-break, least damage taken."""
    def key(item):
        name, mu = item
        return (-mu["best_stab"], not mu["immune_to_wild"], mu["worst_taken"], name)
    return sorted(gt["matchups"].items(), key=key)[0][0]
