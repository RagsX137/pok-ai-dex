# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

The Makefile targets all invoke `.venv/bin/python` explicitly — there is no activation step.

```bash
make run                 # Flask app on http://127.0.0.1:5003
make test-unit           # pytest tests/unit — no server, no network
make test-e2e            # Playwright suite — REQUIRES `make run` in another shell first
make test                # both
make ingest              # re-scrape data/pokemon_db.csv + data/images (rarely needed)
```

Single test / single file:

```bash
.venv/bin/python -m pytest tests/unit/test_coveo_client.py -v
.venv/bin/python -m pytest tests/unit/test_routes.py::test_coveo_proxy_rejects_paths_outside_search -v
```

Eval harness (needs the app running; see `eval_harness/README.md`):

```bash
python -m eval_harness run --label baseline           # draw scenarios, ask, grade, store
python -m eval_harness run --axes no_advantage,zero_damage --probes advantage,pronoun --seed 42
python -m eval_harness report [--run N]               # scoreboard
python -m eval_harness show <turn_id>                 # one turn in full
python -m eval_harness regrade [--run N]              # re-score stored answers, no re-querying
```

There is no linter or formatter configured. `make eval` requires `LABEL=...`.

## Architecture

**Port 5003, not 5000** — macOS Monterey+ reserves 5000 for AirPlay. Override with `POKEDEX_PORT`; tests and the harness read `POKEDEX_URL`.

### Single-definition modules

Three modules exist specifically to be the *only* copy of something. Adding a second copy is the regression these were created to fix:

- `pokedex/config.py` — every port, base URL, pipeline name and directory. `settings` is a frozen dataclass loaded once at import. Nothing else should call `os.getenv` for these values.
- `pokedex/coveo.py` — the only Coveo client. `CoveoClient.search()` and `.generated_answer()` (the full CRGA flow: search → stream ID → SSE). Routes, `agent.py` and the harness all go through it.
- `pokedex/ollama_client.py` — the only `ol.Client` construction.

`pokedex/app.py` is a factory registering four blueprints: `pages` (HTML at `/`, `/dashboard`, `/coach`, `/readme` + static), and `coach`/`coveo`/`llm` all mounted at `/api`.

### The two generative-answer paths

- **`/api/rga-coveo` and `/api/coach`** → Coveo CRGA. `generated_answer()` retries the search up to 6× at 1 s intervals waiting for `extendedResults.generativeQuestionAnsweringId`, then folds the SSE `genqa.*` stream via `parse_genqa_stream`. When no stream ID ever arrives, the *route* builds the "top search excerpts" fallback — the client deliberately returns an empty answer and leaves response shaping to HTTP layer.
- **`/api/rga` and `/api/ask`** → local Ollama, grounded on context the caller supplies. No Coveo call.

`GeneratedAnswer.stream_completed` is tri-state and is **not** Coveo's `answerGenerated` abstention flag — its docstring says so explicitly. Only `eval_harness/backends.py::DirectCoveoClient` reads the real abstention signal.

### Security invariants (each has a comment explaining the bug it fixed)

- `/api/coveo-proxy` validates `path` against `_ALLOWED_PATH`, anchored to `/rest/search/v2*`. The `Authorization` header is attached unconditionally, so a leading `@` in `path` would turn the host into URL userinfo and ship the bearer token elsewhere.
- CORS is scoped to this app's own origins. Reflecting any Origin let any site read `/api/coveo-token`, i.e. the live Coveo key.
- The Coveo token never appears in HTML/JS source; the browser fetches it at runtime from `/api/coveo-token`.
- `/api/set-model` writes process-wide state, so it validates against models actually pulled locally.

### Coach (`/coach`)

`pokedex/routes/coach_api.py` + `pokedex/conversation.py`. Sessions are in-memory only: an `OrderedDict` of `deque(maxlen=20)`, LRU-evicted at 1000 sessions, lost on restart. History is inlined into the RGA query (last 4 turns, assistant turns truncated to 200 chars) so pronouns resolve. Comparison intent is regex-detected before the LLM call; `_STOPWORDS` guards the loose "X or Y" pattern.

`coach_api.py` imports `eval_harness` **optionally** inside a try/except to grade answers for type/chart errors. Grading is best-effort — the app must keep working when `eval_harness` or `eval_data/*.json` is absent.

### PokemonDB facts (`/coach`)

`facts.py` (pure: markdown → `PokemonFacts` → rendered prose), `fact_intent.py`
(message → topic + name) and `facts_store.py` (file → LRU → live) add a third
Coach answer source between the type-chart fast path and CRGA. Answers are
*rendered* from the parsed dataclass, never generated — same rule as
`eval_harness/reference.py`.

`render_answer` returning `None` means "this section was not retrieved" and must
keep falling through to CRGA. Do not make it guess.

Passage text reaches it via `retrieve_passages(..., clean=False)`.
`clean_passage_text` is the dashboard evidence panel'''s transformation and strips
headings and short table cells — exactly what the parser slices on. The two
callers want opposite things from the same API; that is what the flag is for.

`data/pokemon_facts.json` (`make facts`) is optional, like `eval_data/*.json`.

### The type chart lives twice, on purpose

`frontend/modules/type-chart.js` (browser) and `eval_harness/typechart.py` (grader). `tests/unit/test_type_chart_parity.py` parses the JS object literal and asserts all 18×18 cells match. If you edit one, edit both — a drift means either wrong weaknesses in the UI or a grader marking correct answers wrong.

### Frontend

Plain ES modules served from `/frontend/...`; no build step, no bundler. HTML is rendered through `render_template_string` solely to inject `COVEO_ORGANIZATION_ID`.

`frontend/modules/pokemon-panel.js` is the shared panel renderer. **Every DOM function takes an `ns` suffix** appended to element IDs (`''` for the dashboard, `'-a'`/`'-b'` for the coach's comparison panels). New panel rendering belongs here with an `ns` param, not duplicated per page.

Pokémon data has two sources: the Coveo index (search corpus, from `data/pokemon_db.csv`) and PokéAPI (stats/moves/encounters, fetched browser-side after a result is selected, cached in a JS `Map` per session).

### Eval harness

`scenarios.py` draws a team + wild Pokémon constrained by an *axis* (e.g. `no_advantage`, `four_x_defence`) so hard cases are guaranteed rather than lucky; `probes` are the questions asked. Raw answers are the durable asset and grades are always re-derivable — never hand-edit the `grades` table, use `review` (human verdict wins) or fix the grader and `regrade`. Exported "correct answers" come from `reference.py` rendered off the type chart, never from a model.

## Conventions

- Conventional commit subjects: `feat:`, `fix:`, `test:`, `refactor:`, `docs:`.
- Comments in this codebase explain *why* — usually the specific bug or attack a line prevents. Preserve them when editing nearby code; they are not noise.
- Multi-step work is planned in `docs/plans/YYYY-MM-DD-name.md` before implementation.
- Known defects are recorded in `docs/known-issues.md` and pinned with `xfail(strict=True)` rather than deleted — check there before "fixing" a failing e2e test.
- `tests/conftest.py::live_url` **fails rather than skips** when no server is running, so `make test-e2e` can never report green with zero tests run.
