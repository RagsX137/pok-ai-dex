"""
semantic_encoder_report.py
===========================
Report generator (not a pytest test, despite the old test_ name it was moved
from) that confirms the Semantic-PokEncoder (KNN Ranking Function) is active
and contributing to scores on the Coveo 'default' pipeline.

How the encoder actually works
-------------------------------
The model was associated with the 'default' pipeline in Coveo Admin. Coveo
injects it as a Query Ranking Expression (QRE) that computes cosine similarity
between the query vector and each document's pre-computed embedding vector.
The contribution shows up in rankingInfo as "Ranking functions: N".

What this report measures
-------------------------
1. knn_score   — the "Ranking functions" contribution extracted from rankingInfo.
                 Non-zero means the encoder fired for that document.
2. top-3 hit   — whether the expected Pokemon appears in the top 3 results.
3. avg_knn     — average KNN contribution across the top-5, showing signal strength.

Test categories
---------------
exact    : direct name query — keyword + KNN both fire, KNN adds a bonus
semantic : concept/description query — keyword is weak, KNN carries the result
trait    : longer description — hardest case for pure keyword, best for KNN
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

COVEO_ORG   = os.getenv("COVEO_ORGANIZATION_ID", "")
COVEO_TOKEN = os.getenv("COVEO_ACCESS_TOKEN", "")
COVEO_BASE  = f"https://{COVEO_ORG}.org.coveo.com" if COVEO_ORG else "https://platform.cloud.coveo.com"
PIPELINE    = os.getenv("COVEO_PIPELINE", "default")
SEARCH_HUB  = os.getenv("COVEO_SEARCH_HUB", "PokedexUI")
NUM_RESULTS = 5

# Regex to pull "Ranking functions: N" from the rankingInfo string
_KNN_RE = re.compile(r"Ranking functions:\s*(\d+)", re.IGNORECASE)


# ── Coveo REST helper ──────────────────────────────────────────────────────────

def _search(query: str) -> dict:
    url  = f"{COVEO_BASE}/rest/search/v2?organizationId={COVEO_ORG}"
    hdrs = {"Authorization": f"Bearer {COVEO_TOKEN}", "Content-Type": "application/json"}
    body = {
        "q":               query,
        "numberOfResults": NUM_RESULTS,
        "searchHub":       SEARCH_HUB,
        "pipeline":        PIPELINE,
        "debug":           True,
        # The Semantic Encoder runs via the pipeline's KNN Ranking Function —
        # no mlParameters needed.
    }
    r = requests.post(url, json=body, headers=hdrs, timeout=15)
    r.raise_for_status()
    return r.json()


# ── Result model ──────────────────────────────────────────────────────────────

@dataclass
class Hit:
    rank:      int
    title:     str
    score:     float
    knn_score: int   # "Ranking functions" contribution from rankingInfo

    @classmethod
    def from_raw(cls, i: int, r: dict) -> "Hit":
        ri  = r.get("rankingInfo") or ""
        knn = 0
        if isinstance(ri, str):
            m = _KNN_RE.search(ri)
            if m:
                knn = int(m.group(1))
        return cls(
            rank=i + 1,
            title=r.get("title", ""),
            score=r.get("score") or 0.0,
            knn_score=knn,
        )


def _summarise(response: dict) -> list[Hit]:
    return [Hit.from_raw(i, r) for i, r in enumerate(response.get("results", []))]


# ── Test cases ────────────────────────────────────────────────────────────────

@dataclass
class Case:
    query:          str
    expect_in_top3: str
    category:       str = "exact"
    note:           str = ""


TEST_CASES: list[Case] = [
    # ── Exact name ───────────────────────────────────────────────────────────
    Case("pikachu",   "Pikachu",   "exact", "baseline — keyword + KNN"),
    Case("charizard", "Charizard", "exact", "baseline — keyword + KNN"),
    Case("mewtwo",    "Mewtwo",    "exact", "baseline — keyword + KNN"),

    # ── Semantic / concept ───────────────────────────────────────────────────
    Case("electric mouse",        "Pikachu",   "semantic", "type + animal, no name"),
    Case("fire breathing dragon", "Charizard", "semantic", "description, no name"),
    Case("psychic clone legendary","Mewtwo",   "semantic", "lore description"),
    Case("land shark dragon",     "Garchomp",  "semantic", "nickname + type"),
    Case("ghost haunted tower",   "Gengar",    "semantic", "lore, no name"),

    # ── Trait / description (hardest) ────────────────────────────────────────
    Case("fast pokemon that loves to sleep in forests", "Snorlax",   "trait", ""),
    Case("pokemon that evolves using a thunder stone",  "Raichu",    "trait", ""),
    Case("tiny seed pokemon that grows into a flower",  "Bulbasaur", "trait", ""),
]


# ── Runner ────────────────────────────────────────────────────────────────────

@dataclass
class Result:
    case:  Case
    hits:  list[Hit] = field(default_factory=list)
    error: str = ""

    @property
    def passed(self) -> bool:
        return any(self.case.expect_in_top3.lower() in h.title.lower() for h in self.hits[:3])

    @property
    def avg_knn(self) -> float:
        if not self.hits:
            return 0.0
        return sum(h.knn_score for h in self.hits) / len(self.hits)

    @property
    def encoder_active(self) -> bool:
        """True if at least one top-5 result has a non-zero KNN contribution."""
        return any(h.knn_score > 0 for h in self.hits)


def run_all() -> list[Result]:
    results = []
    for case in TEST_CASES:
        r = Result(case=case)
        try:
            r.hits = _summarise(_search(case.query))
        except Exception as exc:
            r.error = str(exc)
        results.append(r)
    return results


# ── Printer ───────────────────────────────────────────────────────────────────

_CAT = {"exact": "EXACT NAME", "semantic": "SEMANTIC", "trait": "TRAIT/DESC"}
_TICK  = "✅"
_CROSS = "❌"


def print_report(results: list[Result]) -> None:
    passed = sum(1 for r in results if r.passed)
    total  = len(results)
    active = sum(1 for r in results if r.encoder_active)

    print("\n" + "═" * 68)
    print("  COVEO SEMANTIC ENCODER — VERIFICATION REPORT")
    print("═" * 68)
    print(f"  Pipeline  : {PIPELINE}   SearchHub: {SEARCH_HUB}")
    print(f"  Model     : Semantic-PokEncoder (KNN Ranking Function)")
    print(f"  Cases     : {total}  |  Top-3 hits: {passed}/{total}  |  Encoder active: {active}/{total}")
    print("═" * 68)

    for r in results:
        label = _CAT.get(r.case.category, r.case.category)
        status = _TICK if r.passed else _CROSS
        enc    = _TICK if r.encoder_active else _CROSS

        print(f"\n[{label}]  \"{r.case.query}\"")
        if r.case.note:
            print(f"  note  : {r.case.note}")
        print(f"  expect: '{r.case.expect_in_top3}' in top-3  {status}   encoder active: {enc}   avg KNN score: {r.avg_knn:.0f}")

        if r.error:
            print(f"  ERROR: {r.error}")
            continue

        for h in r.hits:
            marker = " ◀" if r.case.expect_in_top3.lower() in h.title.lower() else ""
            print(f"    {h.rank}. [{h.knn_score:>4} KNN | {h.score:>5.0f} total]  {h.title}{marker}")

    print("\n" + "═" * 68)
    print(f"  RESULT  {passed}/{total} top-3 hits  |  encoder KNN active on {active}/{total} queries")
    print("═" * 68 + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Verifying Semantic-PokEncoder on Coveo pipeline …")
    results = run_all()
    print_report(results)
