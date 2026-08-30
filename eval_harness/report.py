"""Aggregate scoreboards over collected runs."""
from __future__ import annotations

import json


def _pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "-"


def summarise(store, run_id=None) -> str:
    where, params = ("WHERE r.run_id = ?", (run_id,)) if run_id is not None else ("", ())
    rows = store.q(
        f"""SELECT t.probe, t.backend, t.answer, t.error,
                   COALESCE(g.human_verdict, g.verdict) AS v,
                   g.harmful, g.type_errors, g.chart_errors, g.retrieval_hit,
                   g.f1, s.axis, s.wild, r.run_id, r.label, r.seed
            FROM turns t
            JOIN scenarios s ON s.scenario_id = t.scenario_id
            JOIN runs r ON r.run_id = s.run_id
            LEFT JOIN grades g ON g.turn_id = t.turn_id {where}""",
        params,
    )
    if not rows:
        return "no turns recorded"

    out: list[str] = []
    total = len(rows)
    verdicts = _tally(rows, "v")
    out.append(f"{total} turns" + (f"  (run {run_id})" if run_id is not None else ""))
    out.append("")
    out.append("verdict          count    share")
    for v in ("correct", "partial", "wrong", "abstained", "error"):
        c = verdicts.get(v, 0)
        out.append(f"  {v:<14} {c:>5}   {_pct(c, total):>6}")

    harmful = sum(1 for r in rows if json.loads(r["harmful"] or "[]"))
    contradictions = sum(
        len([e for e in json.loads(r["type_errors"] or "[]") if e.get("severity") == "contradiction"])
        for r in rows
    )
    chart_errs = sum(len(json.loads(r["chart_errors"] or "[]")) for r in rows)
    missed_retrieval = sum(1 for r in rows if r["retrieval_hit"] == 0)
    out += [
        "",
        f"turns recommending a Pokemon that cannot win : {harmful}",
        f"fabricated Pokemon typings                   : {contradictions}",
        f"fabricated type-chart rules                  : {chart_errs}",
        f"turns where the wild Pokemon was not retrieved: {missed_retrieval}",
    ]

    out += ["", "by probe", _hdr()]
    for probe in sorted({r["probe"] for r in rows}):
        sub = [r for r in rows if r["probe"] == probe]
        out.append(_line(probe, sub))

    out += ["", "by backend", _hdr()]
    for backend in sorted({r["backend"] for r in rows}):
        sub = [r for r in rows if r["backend"] == backend]
        out.append(_line(backend, sub))

    out += ["", "by axis", _hdr()]
    for axis in sorted({r["axis"] for r in rows}):
        sub = [r for r in rows if r["axis"] == axis]
        out.append(_line(axis, sub))
    return "\n".join(out)


def _hdr():
    return f"  {'':<18} {'n':>4} {'correct':>8} {'partial':>8} {'wrong':>7} {'abstain':>8} {'mean f1':>8}"


def _line(name, sub):
    t = _tally(sub, "v")
    f1s = [r["f1"] for r in sub if r["f1"] is not None]
    mean = f"{sum(f1s)/len(f1s):.2f}" if f1s else "-"
    return (
        f"  {name:<18} {len(sub):>4} {t.get('correct',0):>8} {t.get('partial',0):>8} "
        f"{t.get('wrong',0):>7} {t.get('abstained',0):>8} {mean:>8}"
    )


def _tally(rows, key):
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def list_runs(store) -> str:
    rows = store.q(
        """SELECT r.run_id, r.started_at, r.seed, r.label, r.backends,
                  COUNT(DISTINCT s.scenario_id) AS n_sc, COUNT(t.turn_id) AS n_turns,
                  SUM(CASE WHEN COALESCE(g.human_verdict,g.verdict)='correct' THEN 1 ELSE 0 END) AS ok
           FROM runs r
           LEFT JOIN scenarios s ON s.run_id = r.run_id
           LEFT JOIN turns t ON t.scenario_id = s.scenario_id
           LEFT JOIN grades g ON g.turn_id = t.turn_id
           GROUP BY r.run_id ORDER BY r.run_id DESC"""
    )
    if not rows:
        return "no runs yet"
    out = [f"{'run':>4}  {'started':<20} {'seed':>10} {'scen':>5} {'turns':>6} {'correct':>8}  label"]
    for r in rows:
        out.append(
            f"{r['run_id']:>4}  {(r['started_at'] or '')[:19]:<20} {r['seed']:>10} "
            f"{r['n_sc']:>5} {r['n_turns']:>6} {(r['ok'] or 0):>8}  {r['label'] or ''}"
        )
    return "\n".join(out)
