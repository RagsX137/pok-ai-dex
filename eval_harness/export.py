"""
Turns collected runs into material for developing the agent.

  sft       - {messages:[user, assistant]} pairs whose assistant turn is the
              chart-derived correct answer. Fine-tuning / distillation targets.
  fewshot   - the failure, why it is wrong, and the corrected answer. Drop
              straight into a system prompt as worked examples.
  failures  - flat rows of everything the harness scored as wrong, for triage.
"""
from __future__ import annotations

import json
from pathlib import Path

from .reference import ideal_answer


def _rows(store, run_id=None, only_failures=False):
    sql = """SELECT t.turn_id, t.probe, t.backend, t.query, t.answer, t.error,
                    t.answer_generated,
                    s.wild, s.team, s.ground_truth, s.axis,
                    g.verdict, g.human_verdict, g.predicted, g.expected,
                    g.harmful, g.type_errors, g.chart_errors, g.retrieval_hit, g.notes
             FROM turns t
             JOIN scenarios s ON s.scenario_id = t.scenario_id
             LEFT JOIN grades g ON g.turn_id = t.turn_id
             WHERE 1=1"""
    params = []
    if run_id is not None:
        sql += " AND s.run_id = ?"
        params.append(run_id)
    if only_failures:
        sql += " AND COALESCE(g.human_verdict, g.verdict) IN ('wrong','partial','abstained')"
    sql += " ORDER BY t.turn_id"
    return store.q(sql, tuple(params))


def _ctx(row):
    gt = json.loads(row["ground_truth"])
    team = json.loads(row["team"])
    return gt, team


def export_sft(store, out_path, run_id=None) -> int:
    """
    Correct answers, keyed to the exact question that was asked.

    The target depends only on the question, so identical queries asked of
    several backends collapse to one training pair.
    """
    n = 0
    seen: set[str] = set()
    with Path(out_path).open("w") as fh:
        for row in _rows(store, run_id):
            if row["query"] in seen:
                continue
            seen.add(row["query"])
            gt, team = _ctx(row)
            target = ideal_answer(row["probe"], gt, team)
            fh.write(json.dumps({
                "messages": [
                    {"role": "user", "content": row["query"]},
                    {"role": "assistant", "content": target},
                ],
                "meta": {
                    "turn_id": row["turn_id"], "probe": row["probe"],
                    "axis": row["axis"], "wild": row["wild"], "team": team,
                    "wild_types": gt["wild_types"],
                    "expected_advantage": gt["advantage"],
                },
            }) + "\n")
            n += 1
    return n


def export_fewshot(store, out_path, run_id=None) -> int:
    """Failure + diagnosis + correction, for prompt engineering."""
    n = 0
    with Path(out_path).open("w") as fh:
        for row in _rows(store, run_id, only_failures=True):
            gt, team = _ctx(row)
            verdict = row["human_verdict"] or row["verdict"]
            diagnosis = []
            for h in json.loads(row["harmful"] or "[]"):
                diagnosis.append(f"recommended {h['pokemon']}, which {h['reason']}")
            for e in json.loads(row["type_errors"] or "[]"):
                if e.get("severity") == "contradiction":
                    diagnosis.append(
                        f"said {e['pokemon']} is {'/'.join(e['claimed'])}, "
                        f"but it is {'/'.join(e['actual'])}"
                    )
            for e in json.loads(row["chart_errors"] or "[]"):
                diagnosis.append(
                    f"claimed {e['claim'].replace('>', 'is super effective against')}, "
                    f"but that matchup is {e['actual_multiplier']:g}x"
                )
            for note in json.loads(row["notes"] or "[]"):
                diagnosis.append(note)
            if row["retrieval_hit"] == 0:
                diagnosis.append(f"the {row['wild']} page was never retrieved")
            fh.write(json.dumps({
                "question": row["query"],
                "bad_answer": row["answer"],
                "verdict": verdict,
                "why_wrong": diagnosis,
                "good_answer": ideal_answer(row["probe"], gt, team),
                "meta": {"turn_id": row["turn_id"], "probe": row["probe"],
                         "backend": row["backend"], "axis": row["axis"]},
            }) + "\n")
            n += 1
    return n


def export_failures(store, out_path, run_id=None) -> int:
    n = 0
    with Path(out_path).open("w") as fh:
        for row in _rows(store, run_id, only_failures=True):
            fh.write(json.dumps({k: row[k] for k in row.keys()}) + "\n")
            n += 1
    return n


EXPORTERS = {"sft": export_sft, "fewshot": export_fewshot, "failures": export_failures}
