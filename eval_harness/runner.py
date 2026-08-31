"""Orchestration: draw scenarios, ask every probe of every backend, store, grade."""
from __future__ import annotations

import random

from .backends import AppClient, DirectCoveoClient
from .grading import Grade, grade_turn
from .scenarios import ScenarioBuilder

HARNESS_VERSION = "1.0.0"
GRADE_METHOD = "heuristic-v1"


class Runner:
    def __init__(self, *, store, chart, pool, app: AppClient,
                 direct: DirectCoveoClient | None = None, verbose: bool = True):
        self.store = store
        self.chart = chart
        self.pool = pool
        self.app = app
        self.direct = direct
        self.verbose = verbose

    def _log(self, msg: str = "") -> None:
        if self.verbose:
            print(msg, flush=True)

    def _dispatch(self, backend: str, query: str):
        if backend == "app-coveo":
            return self.app.ask_coveo(query)
        if backend == "direct-coveo":
            if not (self.direct and self.direct.configured):
                raise RuntimeError("direct-coveo needs COVEO_ORGANIZATION_ID and COVEO_ACCESS_TOKEN")
            return self.direct.ask(query)
        if backend.startswith("app-ollama:"):
            return self.app.ask_ollama(query, backend.split(":", 1)[1])
        raise ValueError(f"unknown backend {backend!r}")

    def run(self, *, seed: int, axes: list[str], probes: list[str],
            backends: list[str], label: str | None = None,
            notes: str | None = None, repeats: int = 1) -> int:
        rng = random.Random(seed)
        builder = ScenarioBuilder(self.pool, self.chart, rng)

        run_id = self.store.start_run(
            seed=seed, harness_version=HARNESS_VERSION, grade_method=GRADE_METHOD,
            app_base_url=self.app.base, backends=backends, axes=axes,
            probes=probes, label=label, notes=notes,
        )
        self._log(f"run {run_id}  seed={seed}  backends={','.join(backends)}")

        ordinal = 0
        for rep in range(repeats):
            for axis in axes:
                sc = builder.draw(axis)
                if sc is None:
                    self._log(f"  ! could not draw a scenario for axis {axis!r}; skipped")
                    continue
                builder.attach_probes(sc, probes)
                ordinal += 1
                scenario_id = self.store.add_scenario(run_id, ordinal, sc)
                gt = sc.ground_truth
                self._log(
                    f"\n[{ordinal}] {axis}  wild={sc.wild} "
                    f"({'/'.join(gt['wild_types'])})  team={', '.join(sc.team)}"
                )
                self._log(f"     expected advantage: {gt['advantage'] or 'NONE'}")

                for t_ord, (probe, query) in enumerate(sc.probes):
                    for backend in backends:
                        try:
                            res = self._dispatch(backend, query)
                        except Exception as exc:  # never lose the rest of the run
                            self._log(f"     [{probe}/{backend}] dispatch failed: {exc}")
                            continue
                        turn_id = self.store.add_turn(scenario_id, t_ord, probe, query, res)
                        g = grade_turn(
                            probe=probe, answer=res.answer, error=res.error,
                            ground_truth=gt, team=sc.team, wild=sc.wild,
                            search_titles=res.search_titles,
                            citation_titles=[c.get("title", "") for c in res.citations],
                            chart=self.chart, answer_generated=res.answer_generated,
                        )
                        self.store.add_grade(turn_id, g)
                        self._report(probe, backend, g, res)

        self.store.finish_run(run_id)
        self._log(f"\nrun {run_id} complete")
        return run_id

    def _report(self, probe: str, backend: str, g: Grade, res) -> None:
        flags = []
        if g.harmful:
            flags.append(f"HARMFUL:{','.join(h['pokemon'] for h in g.harmful)}")
        contradictions = [e for e in g.type_errors if e.get("severity") == "contradiction"]
        if contradictions:
            flags.append(f"typeErr:{len(contradictions)}")
        if g.chart_errors:
            flags.append(f"chartErr:{len(g.chart_errors)}")
        if g.retrieval_hit is False:
            flags.append("no-retrieval")
        self._log(
            f"     [{probe:<12} {backend:<18}] {g.verdict.upper():<9} "
            f"{res.latency_ms:>6}ms  {' '.join(flags)}"
        )

    def regrade(self, run_id: int | None = None) -> int:
        """Re-score stored answers with the current grader. Never re-queries."""
        rows = self.store.turns_for_regrade(run_id)
        import json as _json
        n = 0
        for row in rows:
            gt = _json.loads(row["ground_truth"])
            team = _json.loads(row["team"])
            search, cits = self.store.retrieval_titles(row["turn_id"])
            g = grade_turn(
                probe=row["probe"], answer=row["answer"], error=row["error"],
                ground_truth=gt, team=team, wild=row["wild"],
                search_titles=search, citation_titles=cits, chart=self.chart,
                answer_generated=(
                    None if row["answer_generated"] is None else bool(row["answer_generated"])
                ),
            )
            self.store.add_grade(row["turn_id"], g)
            n += 1
        return n
