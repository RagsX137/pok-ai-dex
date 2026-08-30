"""
eval_llm_comparison.py
======================
Compares Ollama vs Coveo Professor-Oak on Pokémon queries.
Logs each run to MLflow so you can diff them side-by-side.

Metrics logged per answer
--------------------------
  rouge1_f      — unigram overlap with the reference answer
  rouge2_f      — bigram overlap
  rougeL_f      — longest common subsequence
  answer_len    — character length (longer ≠ better, but useful signal)
  latency_s     — wall-clock seconds for the LLM call

Usage
-----
  # Terminal 1 — start MLflow UI
  .venv/bin/mlflow ui --port 5010

  # Terminal 2 — run both models (Flask must be running on port 5003)
  .venv/bin/python scripts/mlflow/compare_llms.py

  # Run only Professor-Oak on a custom cases file
  .venv/bin/python scripts/mlflow/compare_llms.py --coveo-only --cases-file my_cases.json

  # Run only Ollama
  .venv/bin/python scripts/mlflow/compare_llms.py --ollama-only

  # Override the Ollama model
  .venv/bin/python scripts/mlflow/compare_llms.py --ollama-model mistral:7b

Then open http://localhost:5010 and compare runs under "pokedex-llm-comparison".
"""

import argparse
import json
import time
from pathlib import Path

import mlflow
import requests
from rouge_score import rouge_scorer

# ── Defaults ──────────────────────────────────────────────────────────────────

REPO_ROOT           = Path(__file__).resolve().parents[2]
FLASK_BASE          = "http://localhost:5003"
EXPERIMENT          = "pokedex-llm-comparison"
DEFAULT_CASES_FILE  = REPO_ROOT / "data" / "eval_cases" / "core.json"
DEFAULT_OLLAMA_MODEL = "gemma4:12b-mlx"

# ── Scorer ────────────────────────────────────────────────────────────────────

_scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)


def _rouge(answer: str, reference: str) -> dict:
    scores = _scorer.score(reference, answer)
    return {
        "rouge1_f": round(scores["rouge1"].fmeasure, 4),
        "rouge2_f": round(scores["rouge2"].fmeasure, 4),
        "rougeL_f": round(scores["rougeL"].fmeasure, 4),
    }


# ── LLM callers ───────────────────────────────────────────────────────────────

def _call_ollama(query: str, context: list[dict], model: str) -> tuple[str, float]:
    """Call /api/rga (Ollama). Returns (answer, latency_seconds)."""
    t0 = time.time()
    resp = requests.post(
        f"{FLASK_BASE}/api/rga",
        json={"query": query, "context": context, "model": model},
        timeout=300,
    )
    latency = time.time() - t0
    return resp.json().get("answer", ""), latency


def _call_coveo_rga(query: str) -> tuple[str, float]:
    """Call /api/rga-coveo (Professor-Oak). Returns (answer, latency_seconds)."""
    t0 = time.time()
    resp = requests.post(
        f"{FLASK_BASE}/api/rga-coveo",
        json={"query": query},
        timeout=60,
    )
    latency = time.time() - t0
    return resp.json().get("answer", ""), latency


def _coveo_search_context(query: str) -> list[dict]:
    """Get top-5 Coveo results to use as Ollama's context."""
    resp = requests.post(
        f"{FLASK_BASE}/api/coveo-proxy",
        json={"method": "POST", "path": "/rest/search/v2",
              "body": {"q": query, "numberOfResults": 5}},
        timeout=15,
    )
    results = resp.json().get("results", [])
    return [{"title": r.get("title", ""), "excerpt": r.get("excerpt", "")}
            for r in results]


# ── MLflow run ────────────────────────────────────────────────────────────────

def run_evaluation(
    model_label: str,
    cases: list[dict],
    use_coveo_rga: bool,
    ollama_model: str = DEFAULT_OLLAMA_MODEL,
    cases_file: str = str(DEFAULT_CASES_FILE),
) -> None:
    mlflow.set_experiment(EXPERIMENT)

    with mlflow.start_run(run_name=model_label):
        mlflow.log_param("model",         model_label)
        mlflow.log_param("use_coveo_rga", use_coveo_rga)
        mlflow.log_param("num_cases",     len(cases))
        mlflow.log_param("cases_file",    Path(cases_file).name)

        all_rouge1, all_rouge2, all_rougeL, all_latency = [], [], [], []

        # Per-category accumulators  {category: [rouge1_f, ...]}
        cat_rouge1: dict[str, list[float]] = {}

        for i, case in enumerate(cases):
            query     = case["query"]
            reference = case["reference"]
            category  = case.get("category", "unknown")

            print(f"  [{i+1}/{len(cases)}] {query[:70]}")

            if use_coveo_rga:
                answer, latency = _call_coveo_rga(query)
            else:
                context         = _coveo_search_context(query)
                answer, latency = _call_ollama(query, context, ollama_model)

            metrics = _rouge(answer, reference)
            metrics["answer_len"] = len(answer)
            metrics["latency_s"]  = round(latency, 3)

            # Per-query metrics (step-indexed)
            mlflow.log_metrics({f"q{i+1}_{k}": v for k, v in metrics.items()})

            # Raw answer artifact
            mlflow.log_text(
                f"Q: {query}\n\nA: {answer}\n\nRef: {reference}",
                f"answers/q{i+1:03d}.txt",
            )

            all_rouge1.append(metrics["rouge1_f"])
            all_rouge2.append(metrics["rouge2_f"])
            all_rougeL.append(metrics["rougeL_f"])
            all_latency.append(latency)

            cat_rouge1.setdefault(category, []).append(metrics["rouge1_f"])

            print(f"    rouge1={metrics['rouge1_f']:.3f}  "
                  f"rouge2={metrics['rouge2_f']:.3f}  "
                  f"rougeL={metrics['rougeL_f']:.3f}  "
                  f"latency={latency:.1f}s")

        # ── Summary averages ──────────────────────────────────────────────────
        n = len(all_rouge1)
        summary = {
            "avg_rouge1":    round(sum(all_rouge1)  / n, 4),
            "avg_rouge2":    round(sum(all_rouge2)  / n, 4),
            "avg_rougeL":    round(sum(all_rougeL)  / n, 4),
            "avg_latency_s": round(sum(all_latency) / n, 3),
        }
        # Per-category rouge1 averages
        for cat, vals in sorted(cat_rouge1.items()):
            summary[f"cat_{cat}_rouge1"] = round(sum(vals) / len(vals), 4)

        mlflow.log_metrics(summary)

        print(f"\n  avg rouge1={summary['avg_rouge1']:.3f}  "
              f"avg rouge2={summary['avg_rouge2']:.3f}  "
              f"avg latency={summary['avg_latency_s']:.1f}s\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate Ollama and/or Coveo Professor-Oak and log to MLflow."
    )
    p.add_argument(
        "--cases-file",
        default=str(DEFAULT_CASES_FILE),
        help=f"Path to the JSON eval cases file (default: {DEFAULT_CASES_FILE.name})",
    )
    p.add_argument(
        "--ollama-model",
        default=DEFAULT_OLLAMA_MODEL,
        help=f"Ollama model name (default: {DEFAULT_OLLAMA_MODEL})",
    )
    p.add_argument(
        "--ollama-only",
        action="store_true",
        help="Run only the Ollama evaluation.",
    )
    p.add_argument(
        "--coveo-only",
        action="store_true",
        help="Run only the Coveo Professor-Oak evaluation.",
    )
    p.add_argument(
        "--experiment",
        default=EXPERIMENT,
        help=f"MLflow experiment name (default: {EXPERIMENT})",
    )
    return p.parse_args()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args   = _parse_args()
    cases  = json.loads(Path(args.cases_file).read_text(encoding="utf-8"))
    run_ollama = not args.coveo_only
    run_coveo  = not args.ollama_only

    print(f"Experiment  : '{args.experiment}'")
    print(f"Cases file  : {args.cases_file}  ({len(cases)} cases)")
    print(f"Ollama model: {args.ollama_model}")
    print(f"MLflow UI   : http://localhost:5010  (run: .venv/bin/mlflow ui --port 5010)\n")

    if run_coveo:
        print("=== Run: Coveo Professor-Oak ===")
        run_evaluation(
            model_label  = "coveo-professor-oak",
            cases        = cases,
            use_coveo_rga= True,
            cases_file   = args.cases_file,
        )

    if run_ollama:
        print(f"=== Run: Ollama ({args.ollama_model}) ===")
        run_evaluation(
            model_label  = f"ollama-{args.ollama_model}",
            cases        = cases,
            use_coveo_rga= False,
            ollama_model = args.ollama_model,
            cases_file   = args.cases_file,
        )

    print("Done. Open MLflow UI to compare runs.")
