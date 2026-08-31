"""Command line entry point. See `python -m eval_harness --help`."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv

from .backends import AppClient, DirectCoveoClient
from .corpus import Corpus
from .export import EXPORTERS
from .report import list_runs, summarise
from .reference import ideal_answer
from .runner import GRADE_METHOD, Runner
from .scenarios import AXES, DEFAULT_AXES, DEFAULT_PROBES, PROBES
from .store import Store
from .typechart import TypeChart

from pokedex.config import app_url, settings
DATA = settings.repo_root / "eval_data"
DEFAULT_DB = DATA / "pokedex_eval.db"


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m eval_harness",
        description="Repeatable wild-encounter evaluation for the Agentic Pokedex.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python -m eval_harness run --label baseline\n"
            "  python -m eval_harness run --seed 42 --axes no_advantage,zero_damage --repeats 3\n"
            "  python -m eval_harness run --backends app-coveo,direct-coveo,app-ollama:gemma4:12b-mlx\n"
            "  python -m eval_harness report --run 1\n"
            "  python -m eval_harness export sft --out data/sft.jsonl\n"
        ),
    )
    p.add_argument("--db", default=str(DEFAULT_DB), help=f"SQLite path (default {DEFAULT_DB})")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="draw scenarios, ask the app, grade and store")
    r.add_argument("--seed", type=int, default=None, help="omit for a random seed (recorded either way)")
    r.add_argument("--axes", type=_csv, default=DEFAULT_AXES, help=f"default: {','.join(DEFAULT_AXES)}")
    r.add_argument("--probes", type=_csv, default=DEFAULT_PROBES, help=f"default: {','.join(DEFAULT_PROBES)}")
    r.add_argument("--backends", type=_csv, default=["app-coveo"],
                   help="app-coveo | direct-coveo | app-ollama:<model>")
    r.add_argument("--repeats", type=int, default=1, help="passes over the axis list")
    r.add_argument("--label", default=None, help="tag this run, e.g. 'before-typechart-fix'")
    r.add_argument("--notes", default=None)
    r.add_argument("--app", default=app_url())
    r.add_argument("--refresh-corpus", action="store_true", help="re-harvest names from Coveo")
    r.add_argument("--quiet", action="store_true")

    g = sub.add_parser("regrade", help="re-score stored answers with the current grader")
    g.add_argument("--run", type=int, default=None)

    s = sub.add_parser("report", help="scoreboard")
    s.add_argument("--run", type=int, default=None)

    sub.add_parser("runs", help="list runs")

    e = sub.add_parser("export", help="write training / prompting data")
    e.add_argument("format", choices=sorted(EXPORTERS))
    e.add_argument("--out", required=True)
    e.add_argument("--run", type=int, default=None)

    v = sub.add_parser("review", help="attach a human verdict to a turn")
    v.add_argument("turn_id", type=int)
    v.add_argument("verdict", choices=["correct", "partial", "wrong", "abstained", "error"])
    v.add_argument("--notes", default=None)

    sh = sub.add_parser("show", help="print one turn in full, with the ideal answer")
    sh.add_argument("turn_id", type=int)

    sub.add_parser("axes", help="list scenario axes and probes")
    return p


def _chart() -> TypeChart:
    return TypeChart(DATA / "type_cache.json")


def cmd_run(args, store) -> int:
    load_dotenv(settings.repo_root / ".env")
    app = AppClient(args.app)
    if not app.health():
        print(f"error: no app at {args.app} - start it with `python app.py`", file=sys.stderr)
        return 2

    chart = _chart()
    pool = Corpus(app, DATA / "corpus.json").load(refresh=args.refresh_corpus)
    if len(pool) < 20:
        print(f"error: corpus has only {len(pool)} names; try --refresh-corpus", file=sys.stderr)
        return 2
    print(f"corpus: {len(pool)} Pokemon from the live Coveo index")

    unknown_axes = [a for a in args.axes if a not in AXES]
    unknown_probes = [p for p in args.probes if p not in PROBES]
    if unknown_axes or unknown_probes:
        print(f"error: unknown axes {unknown_axes} probes {unknown_probes}", file=sys.stderr)
        return 2

    seed = args.seed if args.seed is not None else random.randrange(2**31)
    direct = DirectCoveoClient(
        os.getenv("COVEO_ORGANIZATION_ID", ""), os.getenv("COVEO_ACCESS_TOKEN", "")
    )
    runner = Runner(store=store, chart=chart, pool=pool, app=app,
                    direct=direct, verbose=not args.quiet)
    run_id = runner.run(seed=seed, axes=args.axes, probes=args.probes,
                        backends=args.backends, label=args.label,
                        notes=args.notes, repeats=args.repeats)
    print()
    print(summarise(store, run_id))
    return 0


def cmd_show(args, store) -> int:
    rows = store.q(
        """SELECT t.*, s.team, s.wild, s.ground_truth, s.axis,
                  g.verdict, g.human_verdict, g.predicted, g.expected, g.harmful,
                  g.type_errors, g.chart_errors, g.retrieval_hit, g.notes
           FROM turns t JOIN scenarios s ON s.scenario_id=t.scenario_id
           LEFT JOIN grades g ON g.turn_id=t.turn_id WHERE t.turn_id=?""",
        (args.turn_id,),
    )
    if not rows:
        print(f"no turn {args.turn_id}", file=sys.stderr)
        return 1
    r = rows[0]
    gt, team = json.loads(r["ground_truth"]), json.loads(r["team"])
    search, cits = store.retrieval_titles(r["turn_id"])
    print(f"turn {r['turn_id']}  probe={r['probe']}  backend={r['backend']}  axis={r['axis']}")
    print(f"wild: {r['wild']} ({'/'.join(gt['wild_types'])})   team: {', '.join(team)}")
    print(f"\nQ: {r['query']}")
    print(f"\nA: {r['answer'] or '(none)'}")
    if r["error"]:
        print(f"\nERROR: {r['error']}")
    print(f"\nretrieved: {' | '.join(t.split(' Pok')[0][:30] for t in search) or '(none)'}")
    print(f"cited    : {' | '.join(t.split(' Pok')[0][:30] for t in cits) or '(none)'}")
    print(f"\nverdict  : {r['human_verdict'] or r['verdict']}")
    print(f"predicted: {json.loads(r['predicted'] or '[]')}")
    print(f"expected : {json.loads(r['expected'] or '[]')}")
    for e in json.loads(r["type_errors"] or "[]"):
        print(f"  type  [{e['severity']}] {e['pokemon']}: said {'/'.join(e['claimed'])}, is {'/'.join(e['actual'])}")
    for e in json.loads(r["chart_errors"] or "[]"):
        print(f"  chart  {e['claim']} is actually {e['actual_multiplier']:g}x")
    for h in json.loads(r["harmful"] or "[]"):
        print(f"  HARMFUL {h['pokemon']}: {h['reason']}")
    print(f"\nideal answer:\n  {ideal_answer(r['probe'], gt, team)}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "axes":
        print("scenario axes (guarantee a matchup shape):")
        for name, (desc, _) in AXES.items():
            print(f"  {name:<16} {desc}")
        print("\nprobes (the question asked):")
        for name, (desc, _) in PROBES.items():
            print(f"  {name:<16} {desc}")
        return 0

    DATA.mkdir(parents=True, exist_ok=True)
    store = Store(args.db)
    try:
        if args.cmd == "run":
            return cmd_run(args, store)
        if args.cmd == "regrade":
            chart = _chart()
            runner = Runner(store=store, chart=chart, pool=[], app=AppClient("http://unused"))
            n = runner.regrade(args.run)
            print(f"re-scored {n} turns with {GRADE_METHOD}")
            print()
            print(summarise(store, args.run))
            return 0
        if args.cmd == "report":
            print(summarise(store, args.run))
            return 0
        if args.cmd == "runs":
            print(list_runs(store))
            return 0
        if args.cmd == "export":
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            n = EXPORTERS[args.format](store, out, args.run)
            print(f"wrote {n} records to {out}")
            return 0
        if args.cmd == "review":
            store.set_human_verdict(args.turn_id, args.verdict, args.notes)
            print(f"turn {args.turn_id} -> {args.verdict}")
            return 0
        if args.cmd == "show":
            return cmd_show(args, store)
    finally:
        store.close()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
