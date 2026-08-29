"""SQLite persistence. Raw answers are the asset; grades are derived and
recomputable, which is why `regrade` can rewrite them in place."""
from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent.parent, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return None


class Store:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_PATH.read_text())
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ── writes ───────────────────────────────────────────────────────────────
    def start_run(self, *, seed, harness_version, grade_method, app_base_url,
                  backends, axes, probes, label=None, notes=None) -> int:
        cur = self.conn.execute(
            """INSERT INTO runs (started_at, seed, harness_version, grade_method,
                                 app_base_url, git_sha, backends, axes, probes, label, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (_now(), seed, harness_version, grade_method, app_base_url, _git_sha(),
             json.dumps(backends), json.dumps(axes), json.dumps(probes), label, notes),
        )
        self.conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int) -> None:
        self.conn.execute("UPDATE runs SET finished_at=? WHERE run_id=?", (_now(), run_id))
        self.conn.commit()

    def add_scenario(self, run_id: int, ordinal: int, sc) -> int:
        cur = self.conn.execute(
            """INSERT INTO scenarios (run_id, ordinal, axis, wild, wild_types, team, ground_truth)
               VALUES (?,?,?,?,?,?,?)""",
            (run_id, ordinal, sc.axis, sc.wild,
             json.dumps(sc.ground_truth["wild_types"]), json.dumps(sc.team),
             json.dumps(sc.ground_truth, default=str)),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_turn(self, scenario_id: int, ordinal: int, probe: str, query: str, res) -> int:
        cur = self.conn.execute(
            """INSERT INTO turns (scenario_id, ordinal, probe, query, backend, answer,
                                  answer_generated, total_hits, latency_ms, error, raw, asked_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (scenario_id, ordinal, probe, query, res.backend, res.answer,
             None if res.answer_generated is None else int(res.answer_generated),
             res.total_hits, res.latency_ms, res.error,
             json.dumps(res.raw, default=str), _now()),
        )
        turn_id = cur.lastrowid
        rows = [(turn_id, "search_result", i, t, None)
                for i, t in enumerate(res.search_titles)]
        rows += [(turn_id, "citation", i, c.get("title", ""), c.get("uri") or c.get("clickUri"))
                 for i, c in enumerate(res.citations)]
        self.conn.executemany(
            "INSERT INTO retrievals (turn_id, kind, rank, title, uri) VALUES (?,?,?,?,?)", rows
        )
        self.conn.commit()
        return turn_id

    def add_grade(self, turn_id: int, g) -> None:
        self.conn.execute(
            """INSERT INTO grades (turn_id, verdict, grade_method, predicted, expected,
                   false_positives, missed, harmful, type_errors, chart_errors,
                   precision, recall, f1, retrieval_hit, notes, graded_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(turn_id) DO UPDATE SET
                   verdict=excluded.verdict, grade_method=excluded.grade_method,
                   predicted=excluded.predicted, expected=excluded.expected,
                   false_positives=excluded.false_positives, missed=excluded.missed,
                   harmful=excluded.harmful, type_errors=excluded.type_errors,
                   chart_errors=excluded.chart_errors, precision=excluded.precision,
                   recall=excluded.recall, f1=excluded.f1,
                   retrieval_hit=excluded.retrieval_hit, notes=excluded.notes,
                   graded_at=excluded.graded_at""",
            (turn_id, g.verdict, g.grade_method, json.dumps(g.predicted),
             json.dumps(g.expected), json.dumps(g.false_positives), json.dumps(g.missed),
             json.dumps(g.harmful), json.dumps(g.type_errors), json.dumps(g.chart_errors),
             g.precision, g.recall, g.f1,
             None if g.retrieval_hit is None else int(g.retrieval_hit),
             json.dumps(g.notes), _now()),
        )
        self.conn.commit()

    def set_human_verdict(self, turn_id: int, verdict: str, notes: str | None = None) -> None:
        self.conn.execute(
            "UPDATE grades SET human_verdict=?, human_notes=? WHERE turn_id=?",
            (verdict, notes, turn_id),
        )
        self.conn.commit()

    # ── reads ────────────────────────────────────────────────────────────────
    def q(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def turns_for_regrade(self, run_id: int | None = None) -> list[sqlite3.Row]:
        sql = """SELECT t.*, s.team, s.wild, s.ground_truth, s.scenario_id
                 FROM turns t JOIN scenarios s ON s.scenario_id=t.scenario_id"""
        params: tuple = ()
        if run_id is not None:
            sql += " WHERE s.run_id=?"
            params = (run_id,)
        return self.q(sql, params)

    def retrieval_titles(self, turn_id: int) -> tuple[list[str], list[str]]:
        rows = self.q("SELECT kind, title FROM retrievals WHERE turn_id=? ORDER BY rank", (turn_id,))
        return ([r["title"] for r in rows if r["kind"] == "search_result"],
                [r["title"] for r in rows if r["kind"] == "citation"])
