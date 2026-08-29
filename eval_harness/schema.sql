PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- One invocation of the harness.
CREATE TABLE IF NOT EXISTS runs (
    run_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT    NOT NULL,
    finished_at      TEXT,
    seed             INTEGER NOT NULL,
    harness_version  TEXT    NOT NULL,
    grade_method     TEXT    NOT NULL,
    app_base_url     TEXT,
    git_sha          TEXT,
    backends         TEXT    NOT NULL,   -- json list
    axes             TEXT    NOT NULL,   -- json list
    probes           TEXT    NOT NULL,   -- json list
    label            TEXT,               -- free-text tag, e.g. "before-typechart-fix"
    notes            TEXT
);

-- A wild encounter: a team of six and the Pokemon they run into.
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    ordinal      INTEGER NOT NULL,
    axis         TEXT    NOT NULL,
    wild         TEXT    NOT NULL,
    wild_types   TEXT    NOT NULL,       -- json list
    team         TEXT    NOT NULL,       -- json list
    ground_truth TEXT    NOT NULL        -- json: per-member multipliers + expected sets
);

-- One question, asked of one backend.
CREATE TABLE IF NOT EXISTS turns (
    turn_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id      INTEGER NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
    ordinal          INTEGER NOT NULL,
    probe            TEXT    NOT NULL,
    query            TEXT    NOT NULL,
    backend          TEXT    NOT NULL,
    answer           TEXT,
    answer_generated INTEGER,            -- Coveo's abstention flag; NULL if unreported
    total_hits       INTEGER,
    latency_ms       INTEGER,
    error            TEXT,
    raw              TEXT,               -- json blob of the full backend response
    asked_at         TEXT NOT NULL
);

-- What retrieval surfaced for a turn: the result grid and the cited sources.
CREATE TABLE IF NOT EXISTS retrievals (
    retrieval_id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id      INTEGER NOT NULL REFERENCES turns(turn_id) ON DELETE CASCADE,
    kind         TEXT    NOT NULL,       -- 'search_result' | 'citation'
    rank         INTEGER NOT NULL,
    title        TEXT,
    uri          TEXT
);

-- Derived, and always re-derivable from `turns` via `regrade`.
CREATE TABLE IF NOT EXISTS grades (
    grade_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id         INTEGER NOT NULL UNIQUE REFERENCES turns(turn_id) ON DELETE CASCADE,
    verdict         TEXT    NOT NULL,    -- correct|partial|wrong|abstained|error
    grade_method    TEXT    NOT NULL,
    predicted       TEXT,                -- json list
    expected        TEXT,                -- json list
    false_positives TEXT,                -- json list
    missed          TEXT,                -- json list
    harmful         TEXT,                -- json list of {pokemon, reason, ...}
    type_errors     TEXT,                -- json list, each with a severity
    chart_errors    TEXT,                -- json list of fabricated effectiveness rules
    precision       REAL,
    recall          REAL,
    f1              REAL,
    retrieval_hit   INTEGER,             -- was the wild Pokemon's page retrieved at all
    notes           TEXT,                -- json list
    graded_at       TEXT NOT NULL,
    human_verdict   TEXT,                -- set by `review`; always wins over `verdict`
    human_notes     TEXT
);

CREATE INDEX IF NOT EXISTS idx_scenarios_run   ON scenarios(run_id);
CREATE INDEX IF NOT EXISTS idx_turns_scenario  ON turns(scenario_id);
CREATE INDEX IF NOT EXISTS idx_turns_backend   ON turns(backend);
CREATE INDEX IF NOT EXISTS idx_turns_probe     ON turns(probe);
CREATE INDEX IF NOT EXISTS idx_retr_turn       ON retrievals(turn_id);
CREATE INDEX IF NOT EXISTS idx_grades_verdict  ON grades(verdict);

-- Everything needed to read one turn in context, without hand-writing joins.
CREATE VIEW IF NOT EXISTS v_turns AS
SELECT
    t.turn_id, t.probe, t.backend, t.query, t.answer, t.error,
    t.answer_generated, t.latency_ms, t.total_hits,
    s.scenario_id, s.axis, s.wild, s.wild_types, s.team,
    r.run_id, r.seed, r.label, r.started_at,
    g.verdict, g.human_verdict,
    COALESCE(g.human_verdict, g.verdict) AS final_verdict,
    g.predicted, g.expected, g.harmful, g.type_errors, g.chart_errors,
    g.precision, g.recall, g.f1, g.retrieval_hit
FROM turns t
JOIN scenarios s ON s.scenario_id = t.scenario_id
JOIN runs      r ON r.run_id      = s.run_id
LEFT JOIN grades g ON g.turn_id   = t.turn_id;
