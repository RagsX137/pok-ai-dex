"""
tune_cosine_threshold.py
========================
Sweeps the KNN cosine threshold (0.70 → 0.85) and measures top-3 hit rate
on each of the 11 test queries.  No pipeline changes needed — each request
injects a `rankingExpressions` override that shadows the pipeline's QRE.

Results are saved to threshold_results.json so you can diff runs over time.

Usage
-----
    python tune_cosine_threshold.py

Output
------
  • Console table: one row per threshold, columns per query category
  • threshold_results.json: full per-query hit data for every threshold
"""

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

COVEO_ORG   = os.getenv("COVEO_ORGANIZATION_ID", "")
COVEO_TOKEN = os.getenv("COVEO_ACCESS_TOKEN", "")
COVEO_BASE  = f"https://{COVEO_ORG}.org.coveo.com" if COVEO_ORG else "https://platform.cloud.coveo.com"
PIPELINE    = os.getenv("COVEO_PIPELINE", "default")
SEARCH_HUB  = os.getenv("COVEO_SEARCH_HUB", "PokedexUI")
NUM_RESULTS = 5
RESULTS_FILE = Path("threshold_results.json")

# The exact KNN vector field name from the pipeline's rankingInfo debug output
KNN_FIELD = "knn_vector_037690fe_cd91_4e3f_961d_3b5c5f25bfb4_embeddings_vector"

# Regex to extract the "Ranking functions: N" contribution
_KNN_RE = re.compile(r"Ranking functions:\s*(\d+)", re.IGNORECASE)

# Thresholds to sweep
THRESHOLDS = [0.70, 0.72, 0.75, 0.78, 0.80, 0.82, 0.85]


# ── QRE builder ───────────────────────────────────────────────────────────────

def _build_qre(min_cosine: float) -> str:
    """
    Builds the same QRE expression Coveo injects, but with a custom threshold.
    Passed via rankingExpressions to override the pipeline's version per-request.
    """
    return (
        f'var min_cosine := {min_cosine};\n'
        f'var min_ranking_modifier := 100.0;\n'
        f'var max_ranking_modifier := 4500.0;\n'
        f'var cos_sim := @{KNN_FIELD};\n'
        f'if (cos_sim >= min_cosine) {{\n'
        f'  var norm_cos := (cos_sim - min_cosine) / (1.0 - min_cosine);\n'
        f'  var score := min_ranking_modifier + norm_cos * (max_ranking_modifier - min_ranking_modifier);\n'
        f'  score\n'
        f'}}'
    )


# ── Coveo REST helper ─────────────────────────────────────────────────────────

def _search(query: str, threshold: float) -> dict:
    url  = f"{COVEO_BASE}/rest/search/v2?organizationId={COVEO_ORG}"
    hdrs = {"Authorization": f"Bearer {COVEO_TOKEN}", "Content-Type": "application/json"}
    body = {
        "q":               query,
        "numberOfResults": NUM_RESULTS,
        "searchHub":       SEARCH_HUB,
        "pipeline":        PIPELINE,
        "debug":           True,
        # Override the pipeline's KNN QRE with our threshold variant.
        # Coveo applies rankingExpressions on top of (and overriding) pipeline QREs
        # of the same name, so the pipeline config is unchanged.
        "rankingExpressions": [
            {"expression": _build_qre(threshold), "modifier": 0}
        ],
    }
    r = requests.post(url, json=body, headers=hdrs, timeout=15)
    r.raise_for_status()
    return r.json()


# ── Test cases ────────────────────────────────────────────────────────────────

@dataclass
class Case:
    query:          str
    expect_in_top3: str
    category:       str   # "exact" | "semantic" | "trait"


TEST_CASES: list[Case] = [
    Case("pikachu",                                    "Pikachu",   "exact"),
    Case("charizard",                                  "Charizard", "exact"),
    Case("mewtwo",                                     "Mewtwo",    "exact"),
    Case("electric mouse",                             "Pikachu",   "semantic"),
    Case("fire breathing dragon",                      "Charizard", "semantic"),
    Case("psychic clone legendary",                    "Mewtwo",    "semantic"),
    Case("land shark dragon",                          "Garchomp",  "semantic"),
    Case("ghost haunted tower",                        "Gengar",    "semantic"),
    Case("fast pokemon that loves to sleep in forests","Snorlax",   "trait"),
    Case("pokemon that evolves using a thunder stone", "Raichu",    "trait"),
    Case("tiny seed pokemon that grows into a flower", "Bulbasaur", "trait"),
]

CATEGORIES = ["exact", "semantic", "trait"]


# ── Runner ────────────────────────────────────────────────────────────────────

@dataclass
class QueryResult:
    query:     str
    expected:  str
    category:  str
    passed:    bool
    top_titles: list[str]
    knn_scores: list[int]


@dataclass
class ThresholdRun:
    threshold:    float
    timestamp:    str
    results:      list[QueryResult] = field(default_factory=list)

    @property
    def total_passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    def passed_for(self, category: str) -> int:
        return sum(1 for r in self.results if r.passed and r.category == category)

    def total_for(self, category: str) -> int:
        return sum(1 for r in self.results if r.category == category)


def _parse_results(resp: dict, expected: str) -> tuple[bool, list[str], list[int]]:
    titles, knn_scores = [], []
    for r in resp.get("results", [])[:NUM_RESULTS]:
        titles.append(r.get("title", ""))
        ri  = r.get("rankingInfo") or ""
        m   = _KNN_RE.search(ri) if isinstance(ri, str) else None
        knn_scores.append(int(m.group(1)) if m else 0)
    passed = any(expected.lower() in t.lower() for t in titles[:3])
    return passed, titles, knn_scores


def run_sweep() -> list[ThresholdRun]:
    runs = []
    for threshold in THRESHOLDS:
        print(f"  threshold={threshold} …", end="", flush=True)
        run = ThresholdRun(
            threshold=threshold,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        for case in TEST_CASES:
            try:
                resp = _search(case.query, threshold)
                passed, titles, knn_scores = _parse_results(resp, case.expect_in_top3)
            except Exception as exc:
                passed, titles, knn_scores = False, [f"ERROR: {exc}"], [0]
            run.results.append(QueryResult(
                query=case.query, expected=case.expect_in_top3,
                category=case.category, passed=passed,
                top_titles=titles, knn_scores=knn_scores,
            ))
        print(f" {run.total_passed}/{len(TEST_CASES)}")
        runs.append(run)
    return runs


# ── Persistence ───────────────────────────────────────────────────────────────

def _load_history() -> list[dict]:
    if RESULTS_FILE.exists():
        return json.loads(RESULTS_FILE.read_text())
    return []


def _save_history(history: list[dict]) -> None:
    RESULTS_FILE.write_text(json.dumps(history, indent=2))


def _run_to_dict(run: ThresholdRun) -> dict:
    return {
        "threshold": run.threshold,
        "timestamp": run.timestamp,
        "total_passed": run.total_passed,
        "by_category": {
            cat: f"{run.passed_for(cat)}/{run.total_for(cat)}"
            for cat in CATEGORIES
        },
        "results": [asdict(r) for r in run.results],
    }


# ── Console report ────────────────────────────────────────────────────────────

def print_table(runs: list[ThresholdRun]) -> None:
    total = len(TEST_CASES)
    cats  = CATEGORIES

    print("\n" + "═" * 66)
    print("  COSINE THRESHOLD SWEEP — RESULTS")
    print("═" * 66)
    print(f"  {'Threshold':>10}  {'Total':>8}  {'Exact':>8}  {'Semantic':>10}  {'Trait':>8}")
    print("  " + "-" * 62)

    best_total = max(r.total_passed for r in runs)
    for run in runs:
        marker = "  ◀ best" if run.total_passed == best_total else ""
        exact_n    = run.total_for("exact")
        semantic_n = run.total_for("semantic")
        trait_n    = run.total_for("trait")
        print(
            f"  {run.threshold:>10.2f}  "
            f"{run.total_passed:>3}/{total:<4}  "
            f"{run.passed_for('exact'):>3}/{exact_n:<4}  "
            f"{run.passed_for('semantic'):>5}/{semantic_n:<4}  "
            f"{run.passed_for('trait'):>4}/{trait_n:<4}"
            f"{marker}"
        )

    print("═" * 66)

    # Show per-query diff between 0.80 (baseline) and best threshold
    baseline = next((r for r in runs if r.threshold == 0.80), None)
    best_run = max(runs, key=lambda r: r.total_passed)
    if baseline and best_run.threshold != 0.80:
        print(f"\n  Changes from 0.80 → {best_run.threshold} (best threshold):")
        for br, bl in zip(best_run.results, baseline.results):
            if br.passed != bl.passed:
                gained = br.passed and not bl.passed
                symbol = "🆕 GAINED" if gained else "⚠️  LOST"
                print(f"    {symbol}  [{br.category}]  \"{br.query}\"")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Sweeping cosine thresholds: {THRESHOLDS}")
    runs = run_sweep()

    print_table(runs)

    # Append this sweep run to persistent history
    history = _load_history()
    sweep_record = {
        "sweep_timestamp": datetime.now(timezone.utc).isoformat(),
        "thresholds": [_run_to_dict(r) for r in runs],
    }
    history.append(sweep_record)
    _save_history(history)
    print(f"Results saved to {RESULTS_FILE}  ({len(history)} sweep(s) recorded)")
