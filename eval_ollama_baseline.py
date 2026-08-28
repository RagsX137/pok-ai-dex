"""Run only the Ollama baseline half of the MLflow comparison."""
import json
import time
from pathlib import Path

import mlflow
import requests
from rouge_score import rouge_scorer
from dotenv import load_dotenv

load_dotenv()

FLASK_BASE  = "http://localhost:5003"
EXPERIMENT  = "pokedex-llm-comparison"
CASES_FILE  = Path(__file__).parent / "eval_cases.json"
CASES       = json.loads(CASES_FILE.read_text())


def _get_first_ollama_model() -> str:
    """Return the name of the first model currently pulled in Ollama."""
    resp = requests.get("http://localhost:11434/api/tags", timeout=5)
    resp.raise_for_status()
    models = resp.json().get("models", [])
    if not models:
        raise RuntimeError("No Ollama models found — run `ollama pull <model>` first.")
    return models[0]["name"]

_scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)


def _rouge(answer, reference):
    s = _scorer.score(reference, answer)
    return {k: round(s[k].fmeasure, 4) for k in ["rouge1", "rouge2", "rougeL"]}


def _context(query):
    r = requests.post(
        f"{FLASK_BASE}/api/coveo-proxy",
        json={"method": "POST", "path": "/rest/search/v2",
              "body": {"q": query, "numberOfResults": 5}},
        timeout=15,
    )
    return [{"title": x.get("title", ""), "excerpt": x.get("excerpt", "")}
            for x in r.json().get("results", [])]


if __name__ == "__main__":
    OLLAMA_MODEL = _get_first_ollama_model()
    print(f"Using Ollama model: {OLLAMA_MODEL}")

    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name=f"ollama-{OLLAMA_MODEL}"):
        mlflow.log_param("model", f"ollama-{OLLAMA_MODEL}")
        mlflow.log_param("num_cases", len(CASES))

        all_r1, all_r2, all_rL, all_lat = [], [], [], []

        for i, case in enumerate(CASES):
            ctx = _context(case["query"])
            t0  = time.time()
            a   = requests.post(
                f"{FLASK_BASE}/api/rga",
                json={"query": case["query"], "context": ctx},
                timeout=90,
            ).json().get("answer", "")
            lat = time.time() - t0

            m = _rouge(a, case["reference"])
            mlflow.log_metrics({f"q{i+1}_rouge1_f": m["rouge1"],
                                 f"q{i+1}_rouge2_f": m["rouge2"],
                                 f"q{i+1}_rougeL_f": m["rougeL"],
                                 f"q{i+1}_latency_s": round(lat, 3),
                                 f"q{i+1}_answer_len": len(a)})
            mlflow.log_text(
                f"Q: {case['query']}\n\nA: {a}\n\nRef: {case['reference']}",
                f"answers/q{i+1:02d}.txt",
            )
            all_r1.append(m["rouge1"]); all_r2.append(m["rouge2"])
            all_rL.append(m["rougeL"]); all_lat.append(lat)

            print(f"  [{i+1}/11] rouge1={m['rouge1']:.3f}  "
                  f"rougeL={m['rougeL']:.3f}  lat={lat:.1f}s  "
                  f"{case['query'][:50]}")

        mlflow.log_metrics({
            "avg_rouge1":    round(sum(all_r1) / len(all_r1), 4),
            "avg_rouge2":    round(sum(all_r2) / len(all_r2), 4),
            "avg_rougeL":    round(sum(all_rL) / len(all_rL), 4),
            "avg_latency_s": round(sum(all_lat) / len(all_lat), 3),
        })

        print(f"\nOllama baseline logged.")
        print(f"  avg rouge1={sum(all_r1)/len(all_r1):.3f}  "
              f"avg rougeL={sum(all_rL)/len(all_rL):.3f}  "
              f"avg latency={sum(all_lat)/len(all_lat):.1f}s")
        print(f"\nRun MLflow UI:  .venv/bin/mlflow ui --port 5010")
