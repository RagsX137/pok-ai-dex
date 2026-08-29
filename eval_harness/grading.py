"""
Automated grading of a free-text answer against the type-chart ground truth.

Two kinds of check live here:

  * Objective, high-confidence checks. Did the answer misstate a Pokemon's own
    typing? Did it assert an effectiveness rule that does not exist? Was the
    wild Pokemon's page retrieved at all? These are exact and need no judgement.

  * A heuristic read of *which teammates the answer actually endorsed*, from
    clause polarity. This is the fuzzy part. Every grade records
    `grade_method`, and the raw answer is stored verbatim, so `regrade` can
    re-score history once this parser improves. `human_verdict` overrides it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .typechart import CHART, TYPES

TYPE_WORDS = "|".join(TYPES)

# LLM answers state typings in several shapes; each of these caught a real
# error during manual evaluation, so all of them are checked.
_T = rf"(?P<t1>{TYPE_WORDS})(?:\s*/\s*(?P<t2>{TYPE_WORDS}))?"
_NAME = r"(?-i:(?P<name>[A-Z][a-zA-Z'\u2019]*(?:\s[A-Z][a-zA-Z'\u2019]*)?))"

# (pattern, mode). "full" asserts the complete typing, so a missing half is an
# omission worth recording. "partial" only ever names one of the types
# ("Vileplume's Poison-type attacks"), so it is checked as a subset.
TYPE_CLAIM_PATTERNS = [
    # "Lugia is a Psychic/Flying type", "Binacle is a Rock/Poison-type Pokemon"
    (re.compile(rf"\b{_NAME}\s+is\s+(?:an?\s+)?{_T}[-\s]?type", re.I), "full"),
    # "...against Chespin, which is a Grass/Ground type Pokemon"
    (re.compile(rf"\b{_NAME}\s*,?\s+which\s+is\s+(?:an?\s+)?{_T}[-\s]?type", re.I), "full"),
    # "Komala (Normal), Buzzwole (Bug/Rock), Altaria (Dragon/Flying)"
    (re.compile(rf"\b{_NAME}\s*\(\s*{_T}\s*(?:type)?\s*\)", re.I), "full"),
    # "Dratini's Dragon-type moves", "Vileplume's Poison-type attacks"
    (re.compile(rf"\b{_NAME}['\u2019]s\s+{_T}[-\s]?type", re.I), "partial"),
]

# "Water is super effective against Dark", "Poison and Flying types have
# advantages over Poison", "Ice types have advantages over Grass"
_ATT = rf"(?P<att>(?:{TYPE_WORDS})(?:\s*(?:,|and|or)\s*(?:{TYPE_WORDS}))*)"
_DFN = rf"(?P<dfn>[A-Za-z'\u2019\s]{{0,30}}?(?:{TYPE_WORDS})(?:\s*/\s*(?:{TYPE_WORDS}))?)"
CHART_CLAIM_RE = re.compile(
    rf"\b{_ATT}(?:[-\s]types?)?(?:\s+moves)?(?:\s*,?\s*which)?\s+"
    rf"(?:is|are|has|have)\s+(?:been\s+)?"
    rf"(?:super[-\s]?effective|effective|advantages?|an?\s+advantage)"
    rf"\s+(?:against|over|on|vs\.?)\s+{_DFN}",
    re.I,
)

NEGATIVE_CUES = [
    "do not have", "don't have", "does not have", "doesn't have", "no type advantage",
    "not have a type advantage", "avoid", "bad idea", "ineffective", "not effective",
    "not very effective", "should not", "shouldn't", "poor choice", "at a disadvantage",
    "would struggle", "not recommended", "is resisted", "are resisted", "weak to",
    "is weak", "are weak", "steer clear", "refrain",
]
POSITIVE_CUES = [
    "type advantage", "super effective", "effective against", "advantage against",
    "advantages over", "strong against", "best choice", "safest", "recommend",
    "would be effective", "can beat", "counter", "good idea", "resists",
]

CLAUSE_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+|,\s*(?=while\b|whereas\b|but\b|however\b|although\b)|"
    r";\s*|\s+(?=However,)|\s+(?=Instead,)|\s+(?=Additionally,)",
    re.I,
)

ABSTAIN_SENTINELS = [
    "(no answer generated)", "(rga model did not trigger",
    "(ai answer unavailable)", "(coveo search error", "(crga stream error",
    "(crga error", "(stream request failed",
]

# Probes whose expected answer is the set of teammates to AVOID, not to send.
INVERTED_PROBES = {"avoid"}


@dataclass
class Grade:
    verdict: str = "wrong"          # correct | partial | wrong | abstained | error
    grade_method: str = "heuristic-v1"
    predicted: list[str] = field(default_factory=list)
    expected: list[str] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    harmful: list[dict] = field(default_factory=list)
    type_errors: list[dict] = field(default_factory=list)
    chart_errors: list[dict] = field(default_factory=list)
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    retrieval_hit: bool | None = None
    notes: list[str] = field(default_factory=list)


def _clause_polarity(clause: str) -> int:
    """+1 endorsing, -1 excluding, 0 neutral. Negative cues win ties."""
    low = clause.lower()
    neg = any(c in low for c in NEGATIVE_CUES)
    pos = any(c in low for c in POSITIVE_CUES)
    if neg:
        return -1
    if pos:
        return 1
    return 0


def extract_endorsed(answer: str, team: list[str], inverted: bool = False) -> list[str]:
    """
    Team members the answer puts forward as its recommendation.

    For an `avoid` probe the question itself is negative, so an endorsement of
    'avoid Pelipper' is a *prediction of Pelipper*: polarity is flipped.
    """
    endorsed: list[str] = []
    for clause in CLAUSE_SPLIT_RE.split(answer or ""):
        pol = _clause_polarity(clause)
        if inverted:
            # 'avoid X' / 'X is a bad idea' are the affirmative answers here.
            pol = -pol if pol else 0
            if _clause_polarity(clause) == 0 and re.search(r"\bavoid\b|\bbad idea\b", clause, re.I):
                pol = 1
        if pol <= 0:
            continue
        for member in team:
            if re.search(rf"\b{re.escape(member)}\b", clause, re.I) and member not in endorsed:
                endorsed.append(member)
    return endorsed


def check_type_claims(answer: str, chart, universe: list[str]) -> list[dict]:
    """Every typing assertion in the answer, verified against PokeAPI."""
    errors: list[dict] = []
    seen: set = set()
    lookup = {n.lower(): n for n in universe}
    for pattern, mode in TYPE_CLAIM_PATTERNS:
        for m in pattern.finditer(answer or ""):
            raw_name = m.group("name").strip()
            name = lookup.get(raw_name.lower())
            if not name:
                continue
            claimed = [m.group("t1").lower()]
            if m.group("t2"):
                claimed.append(m.group("t2").lower())
            key = (name, tuple(sorted(claimed)), mode)
            if key in seen:
                continue
            seen.add(key)
            try:
                actual = chart.types_of(name)
            except Exception:
                continue
            invented = [t for t in claimed if t not in actual]
            if invented:
                severity = "contradiction"
            elif mode == "full" and set(claimed) != set(actual):
                severity = "incomplete"
            else:
                continue
            errors.append({
                "pokemon": name,
                "claimed": claimed,
                "actual": actual,
                "severity": severity,
                "invented": invented,
                "quote": m.group(0).strip(),
            })
    return errors


def check_chart_claims(answer: str) -> list[dict]:
    """Every 'A is super effective against B' assertion, verified against the chart."""
    errors = []
    seen = set()
    for m in CHART_CLAIM_RE.finditer(answer or ""):
        attackers = [t.lower() for t in re.findall(rf"\b({TYPE_WORDS})\b", m.group("att"), re.I)]
        dfn_raw = m.group("dfn") or ""
        defenders = [t.lower() for t in re.findall(rf"\b({TYPE_WORDS})\b", dfn_raw, re.I)]
        if not attackers or not defenders:
            continue
        for att in attackers:
            key = (att, tuple(defenders))
            if key in seen:
                continue
            seen.add(key)
            mult = 1.0
            for d in defenders:
                mult *= CHART[att][d]
            if mult < 2.0:
                errors.append({
                    "claim": f"{att} > {'/'.join(defenders)}",
                    "actual_multiplier": mult,
                    "quote": m.group(0).strip(),
                })
    return errors


def is_abstention(answer: str) -> bool:
    low = (answer or "").strip().lower()
    if not low:
        return True
    return any(low.startswith(s) or low == s for s in ABSTAIN_SENTINELS)


def grade_turn(
    *, probe: str, answer: str, error: str | None, ground_truth: dict,
    team: list[str], wild: str, search_titles: list[str], citation_titles: list[str],
    chart, answer_generated: bool | None = None,
) -> Grade:
    g = Grade()
    universe = list(team) + [wild]

    # Did retrieval surface the Pokemon the question is actually about?
    hay = " || ".join(search_titles + citation_titles).lower()
    g.retrieval_hit = wild.lower() in hay

    if error:
        g.verdict = "error"
        g.notes.append(error)
        return g
    if is_abstention(answer) or answer_generated is False:
        g.verdict = "abstained"
        if answer_generated is False:
            g.notes.append("Coveo set answerGenerated=false (deliberate abstention)")
        return g

    # Objective checks run on every answered turn, lookup included.
    g.type_errors = check_type_claims(answer, chart, universe)
    g.chart_errors = check_chart_claims(answer)

    if probe == "lookup":
        # A lookup is graded on whether it described the right Pokemon correctly.
        wild_wrong = [e for e in g.type_errors if e["pokemon"] == wild]
        named = re.search(rf"\b{re.escape(wild)}\b", answer, re.I) is not None
        if not named:
            g.verdict = "wrong"
            g.notes.append(f"answer never mentions {wild}")
        elif wild_wrong or g.chart_errors:
            g.verdict = "partial"
        else:
            g.verdict = "correct"
        return g

    inverted = probe in INVERTED_PROBES
    g.expected = list(ground_truth["liabilities"] if inverted else ground_truth["advantage"])
    g.predicted = extract_endorsed(answer, team, inverted=inverted)

    pset, eset = set(g.predicted), set(g.expected)
    g.false_positives = sorted(pset - eset)
    g.missed = sorted(eset - pset)

    # A false positive that literally cannot win is worse than a plain miss.
    if not inverted:
        for name in g.false_positives:
            m = ground_truth["matchups"].get(name)
            if not m:
                continue
            if m["dead_types"] or m["is_liability"]:
                g.harmful.append({
                    "pokemon": name,
                    "best_stab": m["best_stab"],
                    "worst_taken": m["worst_taken"],
                    "dead_types": m["dead_types"],
                    "reason": (
                        f"has a {'/'.join(m['dead_types'])} STAB that deals 0x"
                        if m["dead_types"]
                        else f"takes {m['worst_taken']:g}x and hits for only {m['best_stab']:g}x"
                    ),
                })

    tp = len(pset & eset)
    g.precision = tp / len(pset) if pset else (1.0 if not eset else 0.0)
    g.recall = tp / len(eset) if eset else (1.0 if not pset else 0.0)
    g.f1 = (
        2 * g.precision * g.recall / (g.precision + g.recall)
        if (g.precision + g.recall)
        else 0.0
    )

    # The honesty case: correct answer is "none of them".
    if not eset:
        g.verdict = "correct" if not pset else "wrong"
        if pset:
            n = len(pset)
            g.notes.append(
                f"no teammate has a type advantage, but {n} "
                f"{'was' if n == 1 else 'were'} claimed to"
            )
    elif pset == eset and not g.type_errors and not g.chart_errors:
        g.verdict = "correct"
    elif g.harmful or not tp:
        g.verdict = "wrong"
    elif pset == eset:
        g.verdict = "partial"
        g.notes.append("right set, but the stated reasoning contains errors")
    else:
        g.verdict = "partial"
    return g
