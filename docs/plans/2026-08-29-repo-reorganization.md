# Repository Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every file in the Agentic Pokédex repo into a place that matches its role, collapse the duplicated Coveo/config/SSE code into one copy each, and make the whole thing runnable and testable from documented entry points — without changing a single user-visible behaviour.

**Architecture:** The repo currently has three real subsystems (a Flask app, a static frontend, an evaluation harness) plus a scattering of one-off scripts, generated data and a design mockup, all sharing one flat root directory. The reorganization gives each subsystem a package root (`pokedex/`, `frontend/`, `eval_harness/`), moves generated and source data under `data/`, moves scripts under `scripts/`, moves browser checks into a real `tests/` tree, and introduces `pokedex/config.py` + `pokedex/coveo.py` as the single definitions of "where Coveo lives" and "how we talk to it" — currently copied 9 times.

**Tech Stack:** Python 3.11, Flask 3.1, Coveo Search API v2 + CRGA streaming, Ollama, Playwright, pytest, SQLite, Coveo Atomic v3 (CDN, no build step), vanilla ES modules.

**Spec:** This document is self-contained — the "Current State Audit" section below is the spec. It was derived by reading every tracked and untracked file in the repo on 2026-08-29.

## Global Constraints

- **No behaviour changes.** Every route, every URL the browser requests, every CLI flag keeps working identically. This is a move-and-deduplicate exercise, not a redesign. If a task tempts you into a behaviour fix, stop and note it in `docs/known-issues.md` instead.
- **Public URLs are frozen.** `/`, `/dashboard`, `/readme`, `/frontend/<path>`, `/images/<filename>`, `/api/coveo-token`, `/api/coveo-proxy`, `/api/rga`, `/api/rga-coveo`, `/api/ask`, `/api/set-model`, `/api/models`. Browser-facing paths inside HTML/JS (`/frontend/...`, `/images/...`, `/api/...`) do not change even when the files behind them move.
- **Port stays 5003.** macOS reserves 5000 for AirPlay. `5003` must appear in exactly one Python file after this work (`pokedex/config.py`); everywhere else reads it from config or `POKEDEX_URL`.
- **No npm / no build step.** The frontend stays CDN + vanilla ES modules. Do not introduce bundlers, TypeScript, or a `package.json`.
- **`eval_harness/` internals are not restructured.** It is already the cleanest part of the repo. It only gains: an import of shared config, and its data paths pointing at the new `data/` location.
- **Python 3.11.4**, matching the existing `.venv`.
- **One `git mv` per logical group, committed separately.** Never mix a file move with a content edit in the same commit — it destroys `git log --follow` and makes review impossible.
- **The repo is public** (`github.com/RagsX137/pok-ai-dex`). Nothing personal, unrelated, or credential-bearing may remain tracked.

---

## Current State Audit

This is the ground truth the plan works from. Verified 2026-08-29 on branch `optimized-agentic-pokedex`.

### What actually runs in production

| Component | Files | Notes |
|---|---|---|
| Flask server | `app.py` (332 lines) | 12 routes; being actively hardened (SSRF path allowlist, CORS origin pin, `FLASK_DEBUG` gate) |
| Agent loop | `agent.py` (89 lines) | `_coveo_search` → `generate_rga_answer` → `run_agent` |
| Main UI | `frontend/dashboard.{html,css,js}` | **`/dashboard` is the primary entry point** (per `frontend/readme.html:475`) |
| Legacy UI | `frontend/index.html`, `pokedex-atomic.js`, `pokedex-styles.css`, `test-chrome.html` | Served at `/`; still works, still shipped |
| Shared FE module | `frontend/type-colors.js` | Imported by all three JS entry points — the one thing already deduplicated |
| Docs page | `frontend/readme.html` (616 lines) | Served at `/readme`; `README.md` is a 3-line pointer at it |
| Artwork | `pokemon_images/` (1026 files, 74 MB) | Gitignored except `placeholder.png` |
| Eval harness | `eval_harness/` (13 modules + `schema.sql` + `README.md`) | Committed as `d4b20bf` on branch **`data-gathering-eval-harness`** — not present on `optimized-agentic-pokedex`. See Task 0. |
| Eval data | `eval_data/` | `corpus.json` (924 names) + `type_cache.json` (315) committed on `data-gathering-eval-harness`; `.db` + `exports/` gitignored |

### Problems, in descending order of cost

**1. Twenty loose files in the repo root.** A visitor to a public repo sees `test_400s2.py`, `probe_crga2.py`, `check_qre_override.py`, `threshold_results.json` and `keep_active.py` before they see anything that explains the project.

**2. The Coveo client is written nine times.** `COVEO_BASE = f"https://{ORG}.org.coveo.com"` appears in `app.py:24`, `agent.py:16`, `eval_harness/backends.py:161`, `probe_crga.py:23`, `probe_crga2.py:17`, `debug_encoder.py:16`, `check_qre_override.py:12`, `tune_cosine_threshold.py:34`, `test_semantic_encoder.py:40`. Four of those (`app.py:121-262`, `probe_crga.py`, `probe_crga2.py`, `eval_harness/backends.py`) also contain their own copy of the CRGA SSE parser — the same `data:` prefix strip, the same double-`json.loads` of `payload`, the same `genqa.messageType` / `genqa.citationsType` / `genqa.endOfStreamType` dispatch. A fix to the stream parser today has to be made in four places.

**3. `pytest` cannot be run at the repo root.** Seven root files match `test_*.py`. Five of them (`test_400s.py`, `test_400s2.py`, `test_diag.py`, `test_diag2.py`, `test_dashboard_review.py`) run Playwright at **module import time**, so pytest collection alone launches headless Chromium and hangs waiting for a server on :5003. `test_search.py::test_search(query, expected_fragment)` is collected as a test and errors on two missing fixtures. `.pytest_cache/v/cache/nodeids` confirms this is the only thing pytest has ever collected.

**4. No dependency manifest.** No `requirements.txt`, no `pyproject.toml`, no lockfile. The project needs `flask`, `flask-cors`, `python-dotenv`, `requests`, `ollama`, `mlflow`, `rouge-score`, `pandas`, `beautifulsoup4`, `playwright` — discoverable only by grepping imports.

**5. `legacy_experiments/` is misnamed and holds live assets.** `pokemon_db.csv` (1024 rows) is the **source corpus that was indexed into Coveo** — it is the most important data file in the repo. `pokemon_db_image_scraper.py` generated all of `pokemon_images/`. These are the ingestion pipeline, not experiments. `pokedex_tools.py` in the same folder genuinely is dead — nothing imports it (only `docs/superpowers/plans/2025-07-29-...md:512` mentions it, as a plan that was never taken).

**6. Generated output committed at the root.** `threshold_results.json` (66 KB, output of `tune_cosine_threshold.py`) is tracked. `mlruns/` (4.1 MB of MLflow runs) is gitignored but sitting in the working tree.

**7. `keep_active.py` is a mouse jiggler.** It nudges the cursor to keep a Teams status green. It is unrelated to the Pokédex, it is listed in `.gitignore`, **and it is tracked anyway** (gitignore does not apply to already-tracked files) — so it is published on a public repo.

**8. `pok-dex-redesign-version-2b-dark-dashboard-refined.html` (26 KB) sits in the root.** It is the standalone design mockup that `dashboard.{html,css,js}` were derived from. It is a design document, not application code.

**9. `frontend/dashboard.js` is 1441 lines** holding nine unrelated concerns: an 18×18 type chart, a region/generation map lookup table, a pokemondb.net URL slugifier, a PokéAPI client, facet-filter wiring, result-list rendering, stat/move/effectiveness panels, RGA fetching, and map pan/zoom.

**10. `frontend/result-template.js` is dead.** Nothing imports it. `index.html` uses an inline `<atomic-result-template>` instead.

**11. The type chart exists twice, in two languages, with no parity check.** `frontend/dashboard.js:19-38` (sparse JS object, "omitted = ×1") and `eval_harness/typechart.py:24+` (`_RELATIONS` triples). If one is edited the UI and the grader silently disagree.

**12. Port and base URL hardcoded in twelve places.** `5003` in `app.py`, `eval_llm_comparison.py`, `eval_ollama_baseline.py`, `eval_harness/cli.py`, and all six Playwright scripts.

**13. `docs/` has one file and a five-level-deep plan path** (`docs/superpowers/plans/`), while the substantive documentation lives in a 616-line HTML file inside `frontend/`.

### What is deliberately NOT changing

- `eval_harness/` module layout, CLI surface, and SQLite schema.
- The `/frontend/<path>` URL prefix (so `<script src="/frontend/dashboard.js">` keeps working from any subdirectory, because the route is `<path:filename>`).
- The `/images/<filename>` URL prefix.
- Coveo pipeline names, search hub, field names.

---

## Target File Structure

```
pok-ai-dex/
├── README.md                      # a real README (currently 3 lines)
├── Makefile                       # run / test / eval / ingest / lint
├── pyproject.toml                 # deps + pytest config + ruff config
├── .env.example
├── .gitignore
│
├── pokedex/                       # ← the Flask application package
│   ├── __init__.py
│   ├── __main__.py                # `python -m pokedex`
│   ├── config.py                  # THE definition of ports, URLs, env
│   ├── app.py                     # create_app(), blueprint registration
│   ├── coveo.py                   # CoveoClient: search() + stream_answer()  ← 1 copy
│   ├── ollama_client.py           # chat(), list_models()
│   ├── agent.py                   # run_agent()
│   └── routes/
│       ├── __init__.py
│       ├── pages.py               # /, /dashboard, /readme, /frontend/*, /images/*
│       ├── coveo_api.py           # /api/coveo-token, /api/coveo-proxy, /api/rga-coveo
│       └── llm_api.py             # /api/rga, /api/ask, /api/set-model, /api/models
│
├── frontend/                      # ← static assets; URL prefix unchanged
│   ├── dashboard.html
│   ├── dashboard.css
│   ├── dashboard.js               # orchestration only, ~350 lines
│   ├── modules/
│   │   ├── type-colors.js         # moved, unchanged
│   │   ├── type-chart.js          # extracted from dashboard.js
│   │   ├── regions.js             # VERSION_GEN, REGION_MAP_IMG, GEN_LABEL, …
│   │   ├── pokeapi.js             # fetchPokeData, fetchLocationsByGen, fetchMoveType
│   │   ├── pokemondb.js           # pokeSlug, artwork/sprite URL builders
│   │   ├── filters.js             # type chips, generation list, advanced query
│   │   ├── results.js             # result list render + selection
│   │   ├── panels.js              # stats, moves, effectiveness, photo card
│   │   ├── map-card.js            # toggles, region render, pan/zoom
│   │   └── rga.js                 # /api/rga + /api/rga-coveo + model selector
│   ├── classic/                   # ← the original device UI, self-contained
│   │   ├── index.html
│   │   ├── pokedex-styles.css
│   │   ├── pokedex-atomic.js
│   │   └── test-chrome.html
│   └── readme.html
│
├── eval_harness/                  # unchanged internals
├── eval_data/                     # corpus.json, type_cache.json (committed)
│                                  # pokedex_eval.db, exports/ (ignored)
│
├── data/
│   ├── pokemon_db.csv             # ← from legacy_experiments/ — the Coveo source corpus
│   ├── images/                    # ← from pokemon_images/ (gitignored, placeholder.png kept)
│   └── eval_cases/
│       ├── core.json              # ← eval_cases.json (411 cases)
│       └── additional.json        # ← additional_eval_cases.json (390 cases)
│
├── scripts/
│   ├── ingest/
│   │   ├── scrape_pokedex.py      # ← legacy_experiments/pokemon_db.py
│   │   └── scrape_images.py       # ← legacy_experiments/pokemon_db_image_scraper.py
│   ├── coveo/
│   │   ├── probe_crga.py          # ← probe_crga.py + probe_crga2.py merged
│   │   ├── debug_encoder.py
│   │   ├── check_qre_override.py
│   │   ├── tune_cosine_threshold.py
│   │   └── semantic_encoder_report.py   # ← test_semantic_encoder.py (renamed: not a test)
│   └── mlflow/
│       ├── compare_llms.py        # ← eval_llm_comparison.py
│       └── ollama_baseline.py     # ← eval_ollama_baseline.py
│
├── tests/
│   ├── conftest.py                # app fixture, live-server fixture
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_coveo_client.py
│   │   ├── test_routes.py
│   │   └── test_type_chart_parity.py
│   └── e2e/
│       ├── conftest.py            # playwright page fixture + server guard
│       ├── test_dashboard_load.py
│       ├── test_dashboard_search.py
│       ├── test_type_effectiveness.py
│       └── test_filters_and_map.py
│
├── docs/
│   ├── architecture.md            # data-flow doc, replaces tribal knowledge
│   ├── known-issues.md            # parking lot for behaviour bugs found during the move
│   ├── design/
│   │   └── pokedex-v2b-mockup.html    # ← the root HTML mockup
│   ├── plans/                     # ← flattened from docs/superpowers/plans/
│   └── readme-preview.png
│
└── artifacts/                     # gitignored: mlruns/, threshold_results.json, screenshots/
```

**Deleted outright:** `keep_active.py`, `frontend/result-template.js`, `legacy_experiments/pokedex_tools.py`, `test_400s.py`, `test_400s2.py`, `test_diag.py`, `probe_crga2.py` (merged), `threshold_results.json` (regenerable; moves to gitignored `artifacts/`).

---

## Task Sequencing Rationale

Task 0 is a hard prerequisite: a third of the codebase currently lives on a second branch, and reorganizing one branch while the other holds `eval_harness/` guarantees conflicts in every moved path. Tasks 1–3 then build the safety net. **Do not move a single file before Task 3 is green** — without a runnable smoke test there is no way to tell a broken move from a broken environment. Tasks 4–8 are pure moves (verified by the safety net after each). Tasks 9–12 are the deduplication, which is where the real risk lives, so it comes last and each step has a test. Tasks 13–14 are documentation.

---

## Task 0: Reconcile the branches before anything else

**Files:** none created — this task only merges.

**Interfaces:**
- Produces: a single working tree containing the Flask app, the frontend, **and** `eval_harness/` + `eval_data/*.json`. Every later task assumes all three are present.

The evaluation harness and its two cache files were committed to branch
`data-gathering-eval-harness` (commit `d4b20bf`, 4050 insertions across 18 files)
while the app work continued on `optimized-agentic-pokedex`. That commit also
carries the `.gitignore` rules for `eval_data/*.db` and `eval_data/exports/`.
Reorganizing one branch while the other holds a third of the codebase produces a
merge conflict in every moved path later.

- [ ] **Step 1: Confirm what each branch holds**

```bash
git log --oneline -1 data-gathering-eval-harness
git diff --stat optimized-agentic-pokedex data-gathering-eval-harness
```

Expected: `d4b20bf feat: repeatable eval harness for Pokédex battle advice`, and a
diff limited to `.gitignore`, `eval_data/*.json` and `eval_harness/*`.

- [ ] **Step 2: Confirm the in-flight app work has landed**

Already done — commit `30ee8d3` ("fix: correct type effectiveness, stale panels,
filters, and API hardening") carries it. Verify the tree is clean of app changes
before merging:

```bash
git log --oneline -1
git status --short
```

Expected: HEAD is `30ee8d3` or later, and no modified tracked files. Untracked
throwaway `test_*.py` files are expected and are removed in Task 4.

- [ ] **Step 3: Merge the harness branch in**

```bash
git merge data-gathering-eval-harness
```

Expected: a clean merge — the two branches touch disjoint file sets apart from
`.gitignore`. If `.gitignore` conflicts, keep **both** sides' rules.

- [ ] **Step 4: Reconcile the untracked `requirements.txt`**

An untracked `requirements.txt` appeared during the hardening pass:

```
Flask==3.1.3
flask-cors==6.0.5
ollama==0.6.2
playwright==1.62.0
python-dotenv==1.2.3
requests==2.34.2
```

It was committed in `30ee8d3`. **Ruling (pre-flight): it stays.** It is pinned
and correct for the runtime; `pyproject.toml` becomes the authoritative
dependency declaration and adds only what `requirements.txt` omits —
`beautifulsoup4`, `pandas`, `mlflow`, `rouge-score`, needed by `scripts/ingest/`
and `scripts/mlflow/`. Do not delete `requirements.txt`.

- [ ] **Step 5: Verify the merged tree**

```bash
ls eval_harness/*.py | wc -l          # expect 12
.venv/bin/python -m eval_harness runs # expect the stored run list
.venv/bin/python app.py &             # expect a clean boot on :5003
```

- [ ] **Step 6: Commit the merge**

```bash
git status --short
git log --oneline -3
```

The merge commit is the starting point for every task below. Note its SHA — if
the reorganization has to be abandoned, `git reset --hard <that SHA>` restores it.

---

## Task 1: Dependency manifest and project metadata

**Files:**
- Create: `pyproject.toml`
- Create: `requirements-dev.txt`
- Modify: `.gitignore`

**Interfaces:**
- Produces: a `pytest` invocation that collects **only** `tests/`, which every later task depends on. Produces `pip install -e .` as the setup path.

- [ ] **Step 1: Capture the actual dependency set**

Start from the pinned `requirements.txt` that already exists (Task 0 Step 4) and widen it — it covers the runtime but not the scripts.

Run and read the output — do not guess:

```bash
grep -rhoE "^(import|from) [a-zA-Z_][a-zA-Z0-9_]*" --include="*.py" . \
  | grep -v "\.venv" | awk '{print $2}' | sort -u
```

Expected third-party names: `bs4`, `dotenv`, `flask`, `flask_cors`, `mlflow`, `ollama`, `pandas`, `playwright`, `requests`, `rouge_score`.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "pokedex"
version = "0.1.0"
description = "Agentic Pokedex - Coveo semantic search with Ollama and Coveo RGA"
requires-python = ">=3.11"
dependencies = [
    "flask>=3.1",
    "flask-cors>=6.0",
    "python-dotenv>=1.0",
    "requests>=2.32",
    "ollama>=0.4",
]

[project.optional-dependencies]
ingest = ["beautifulsoup4>=4.15", "pandas>=2.2"]
mlflow = ["mlflow>=3.0", "rouge-score>=0.1"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["pokedex*", "eval_harness*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
    "e2e: requires a running server on POKEDEX_URL and a Playwright browser",
]
```

The `testpaths = ["tests"]` line is the fix for audit item 3 — it stops pytest from ever collecting the root `test_*.py` files, even before those files move.

- [ ] **Step 3: Write `requirements-dev.txt`**

```
-e .[ingest,mlflow]
pytest>=8.0
playwright>=1.48
```

- [ ] **Step 4: Verify pytest no longer detonates**

```bash
mkdir -p tests && touch tests/__init__.py
.venv/bin/python -m pytest --collect-only
```

Expected: `no tests ran` / `collected 0 items`. Specifically **not** a hanging headless Chromium and **not** a fixture error from `test_search.py`.

- [ ] **Step 5: Add `artifacts/` to `.gitignore`**

Append:

```gitignore
# Generated outputs — regenerable, never committed
artifacts/
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml requirements-dev.txt .gitignore tests/__init__.py
git commit -m "build: add pyproject with deps and pytest scoped to tests/"
```

---

## Task 2: Test fixtures — app under test and live server

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/e2e/__init__.py`, `tests/e2e/conftest.py`
- Create: `tests/unit/__init__.py`

**Interfaces:**
- Produces: `flask_app` fixture (a Flask test client, no network), `live_url` fixture (a string base URL, skips the test if nothing is listening), `page` fixture (a Playwright page with the dashboard loaded and settled).
- Consumed by: every test in Tasks 3, 9, 10, 11, 12.

- [ ] **Step 1: Write `tests/conftest.py`**

```python
import os
import pytest
import requests


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.getenv("POKEDEX_URL", "http://127.0.0.1:5003")


@pytest.fixture(scope="session")
def live_url(base_url: str) -> str:
    """Base URL of an already-running server, or skip the test."""
    try:
        if requests.get(base_url + "/", timeout=5).status_code != 200:
            pytest.skip(f"no app responding at {base_url}")
    except requests.RequestException:
        pytest.skip(f"no app at {base_url} - start it with `make run`")
    return base_url
```

- [ ] **Step 2: Write `tests/e2e/conftest.py`**

```python
import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def dashboard(browser, live_url):
    """A dashboard page that has finished its default Bulbasaur load."""
    page = browser.new_page()
    page.goto(f"{live_url}/dashboard")
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_function(
        "() => document.querySelector('#rp-name')?.textContent.trim() "
        "&& document.querySelector('#rp-name').textContent.trim() !== '—'",
        timeout=25000,
    )
    yield page
    page.close()
```

`pytest.importorskip` means a machine without Playwright installed still runs the unit tests instead of erroring out.

- [ ] **Step 3: Verify collection still works**

```bash
.venv/bin/python -m pytest --collect-only
```

Expected: `collected 0 items` with no errors.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add app, live-server and playwright fixtures"
```

---

## Task 3: The safety-net smoke test

**Files:**
- Create: `tests/e2e/test_dashboard_load.py`

**Interfaces:**
- Consumes: `dashboard`, `live_url` fixtures from Task 2.
- Produces: the single command every later task runs to prove nothing broke.

This test replaces the ad-hoc checks in `test_dashboard_review.py:53-115`. It is deliberately small — it is a tripwire, not a test suite. The full behavioural suite lands in Task 12.

- [ ] **Step 1: Write the smoke test**

```python
import pytest

pytestmark = pytest.mark.e2e


def test_dashboard_serves(live_url):
    import requests
    r = requests.get(f"{live_url}/dashboard", timeout=10)
    assert r.status_code == 200
    assert "atomic-search-interface" in r.text


def test_static_assets_and_images_serve(live_url):
    import requests
    assert requests.get(f"{live_url}/frontend/dashboard.css", timeout=10).status_code == 200
    assert requests.get(f"{live_url}/images/placeholder.png", timeout=10).status_code == 200


def test_classic_ui_still_serves(live_url):
    import requests
    r = requests.get(f"{live_url}/", timeout=10)
    assert r.status_code == 200
    assert "pokedex-device" in r.text


def test_default_load_populates_panels(dashboard):
    assert "Bulbasaur" in dashboard.locator("#rp-name").inner_text()
    assert dashboard.locator("#type-grid .tchip").count() == 18
    assert dashboard.locator("#gen-list .gen-item").count() == 9
    assert dashboard.locator("#stat-bars .srow2").count() == 6
    assert dashboard.locator("#weak-chips .echip").count() > 0
```

- [ ] **Step 2: Confirm the selectors are real before trusting the test**

The class names above are read from `frontend/dashboard.js` and `test_dashboard_review.py`. Verify each one resolves against the live DOM rather than assuming:

```bash
.venv/bin/python app.py &   # or make run
.venv/bin/python -m pytest tests/e2e/test_dashboard_load.py -v
```

If a selector count is wrong, **fix the test to match reality** — do not change the app. Record the corrected selector in the test.

- [ ] **Step 3: Run it and require green**

Run: `.venv/bin/python -m pytest tests/e2e -v`
Expected: 4 passed. If any fail, the pre-existing app is broken and must be fixed before any move begins.

- [ ] **Step 4: Add the `Makefile`**

```makefile
.PHONY: run test test-unit test-e2e eval lint

run:
	.venv/bin/python -m pokedex

test:
	.venv/bin/python -m pytest

test-unit:
	.venv/bin/python -m pytest tests/unit -v

test-e2e:
	.venv/bin/python -m pytest tests/e2e -v

eval:
	.venv/bin/python -m eval_harness run --label $(LABEL)

ingest:
	.venv/bin/python scripts/ingest/scrape_pokedex.py
	.venv/bin/python scripts/ingest/scrape_images.py
```

`make run` targets `python -m pokedex`, which does not exist until Task 9. Until then it will fail; that is expected and is the reminder that Task 9 is unfinished. Note this in a comment in the Makefile.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_dashboard_load.py Makefile
git commit -m "test: add dashboard smoke test as the reorg safety net"
```

**From here on, every task ends by running `make test-e2e` and requiring green.**

---

## Task 4: Remove the files that should not exist

**Files:**
- Delete: `keep_active.py`, `frontend/result-template.js`, `legacy_experiments/pokedex_tools.py`, `test_400s.py`, `test_400s2.py`, `test_diag.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: nothing. This task only removes.

Each deletion is justified by the audit. Confirm each before removing.

- [ ] **Step 1: Prove `result-template.js` is unreferenced**

```bash
grep -rn "result-template" frontend/ app.py
```

Expected: hits only in `frontend/readme.html` (a docs table) — no `import` and no `<script src>`. If any live reference appears, skip this deletion and note it.

- [ ] **Step 2: Prove `pokedex_tools.py` is unimported**

```bash
grep -rn "pokedex_tools" --include="*.py" . | grep -v "\.venv"
```

Expected: no hits outside `docs/`.

- [ ] **Step 3: Delete**

```bash
git rm keep_active.py frontend/result-template.js legacy_experiments/pokedex_tools.py
rm -f test_400s.py test_400s2.py test_diag.py
```

`test_400s.py`, `test_400s2.py` and `test_diag.py` are untracked one-shot debuggers written on 2026-08-29 to trace two HTTP 400s; they contain no assertions worth keeping. `test_diag2.py` and `test_dashboard_review.py` **do** contain 60+ real behavioural assertions and are kept until Task 12 converts them.

- [ ] **Step 4: Remove the now-stale `keep_active.py` line from `.gitignore`**

Delete the `keep_active.py` line — the file is gone, and the entry was misleading anyway (it never suppressed the file, because the file was already tracked).

- [ ] **Step 5: Verify and commit**

```bash
.venv/bin/python -m pytest tests/e2e -v   # still 4 passed
git add -A
git commit -m "chore: remove dead code and unrelated personal utility

- keep_active.py: mouse jiggler, unrelated to this project, was published
  on a public repo despite a .gitignore entry that never applied to it
- frontend/result-template.js: no importer; index.html uses an inline template
- legacy_experiments/pokedex_tools.py: never imported
- test_400s*.py, test_diag.py: throwaway debuggers, no assertions"
```

---

## Task 5: Move data files under `data/`

**Files:**
- Move: `legacy_experiments/pokemon_db.csv` → `data/pokemon_db.csv`
- Move: `pokemon_images/` → `data/images/`
- Move: `eval_cases.json` → `data/eval_cases/core.json`
- Move: `additional_eval_cases.json` → `data/eval_cases/additional.json`
- Modify: `app.py` (`IMAGES_DIR`), `.gitignore`, `eval_llm_comparison.py`, `eval_ollama_baseline.py`

**Interfaces:**
- Produces: `data/` as the single home for source and reference data. The `/images/<filename>` URL is unchanged — only the directory behind it moves.

- [ ] **Step 1: Move the CSV and image directory**

```bash
mkdir -p data
git mv legacy_experiments/pokemon_db.csv data/pokemon_db.csv
git mv pokemon_images data/images
```

`git mv` on `pokemon_images/` only stages `placeholder.png` (the sole tracked file); the other 1025 JPEGs move on the filesystem and stay ignored.

- [ ] **Step 2: Update `IMAGES_DIR` in `app.py`**

Change line 20 from:

```python
IMAGES_DIR   = Path(__file__).parent / "pokemon_images"
```

to:

```python
IMAGES_DIR   = Path(__file__).parent / "data" / "images"
```

This is the only code reference to the directory. Confirm with:

```bash
grep -rn "pokemon_images" --include="*.py" --include="*.js" --include="*.html" . | grep -v "\.venv"
```

Expected remaining hits: `.gitignore`, `frontend/readme.html:484` (docs prose), `scripts/ingest/scrape_images.py` output path, `docs/superpowers/plans/2025-07-29-...md`. Update `.gitignore` (`pokemon_images/` → `data/images/`) and the scraper's output path now; leave the docs for Task 14.

- [ ] **Step 3: Verify images still serve**

```bash
.venv/bin/python -m pytest tests/e2e/test_dashboard_load.py::test_static_assets_and_images_serve -v
```

Expected: PASS. This is exactly why Task 3 came first.

- [ ] **Step 4: Move the eval-case corpora**

```bash
mkdir -p data/eval_cases
git mv eval_cases.json data/eval_cases/core.json
git mv additional_eval_cases.json data/eval_cases/additional.json
```

- [ ] **Step 5: Repoint the two MLflow scripts**

In `eval_llm_comparison.py:48`:

```python
DEFAULT_CASES_FILE = Path(__file__).parent / "eval_cases.json"
```

becomes (these files move to `scripts/mlflow/` in Task 7, so anchor on the repo root rather than the file):

```python
REPO_ROOT          = Path(__file__).resolve().parents[2]
DEFAULT_CASES_FILE = REPO_ROOT / "data" / "eval_cases" / "core.json"
```

Apply the same change to `eval_ollama_baseline.py:15`. `parents[2]` is correct **after** the Task 7 move (`scripts/mlflow/x.py` → repo root); until then the files are still at the root, so do this edit as part of Task 7 instead and only move the JSON here. Note it in the commit message so the next task picks it up.

- [ ] **Step 6: Run the full smoke test and commit**

```bash
.venv/bin/python -m pytest tests/e2e -v
git add -A
git commit -m "refactor: move source data under data/

pokemon_db.csv is the corpus indexed into Coveo, not a legacy experiment.
/images/<file> URL is unchanged; only IMAGES_DIR moves."
```

---

## Task 6: Move the design mockup and generated output into `docs/` and `artifacts/`

**Files:**
- Move: `pok-dex-redesign-version-2b-dark-dashboard-refined.html` → `docs/design/pokedex-v2b-mockup.html`
- Move: `threshold_results.json` → `artifacts/threshold_results.json` (and untrack)
- Move: `mlruns/` → `artifacts/mlruns/`
- Move: `docs/superpowers/plans/*` → `docs/plans/`
- Modify: `tune_cosine_threshold.py` (`RESULTS_FILE`), `.gitignore`

- [ ] **Step 1: Move the mockup**

```bash
mkdir -p docs/design
git mv pok-dex-redesign-version-2b-dark-dashboard-refined.html \
       docs/design/pokedex-v2b-mockup.html
```

Add a one-line HTML comment at the top of the moved file recording its provenance:

```html
<!-- Design mockup that frontend/dashboard.{html,css,js} were derived from.
     Standalone: open directly in a browser. Not served by the app. -->
```

- [ ] **Step 2: Untrack the generated threshold results**

```bash
mkdir -p artifacts
git rm --cached threshold_results.json
mv threshold_results.json artifacts/threshold_results.json
mv mlruns artifacts/mlruns
```

- [ ] **Step 3: Repoint `tune_cosine_threshold.py:38`**

```python
RESULTS_FILE = Path("threshold_results.json")
```

becomes (relative-to-CWD is a bug waiting to happen — anchor it):

```python
REPO_ROOT    = Path(__file__).resolve().parents[2]
RESULTS_FILE = REPO_ROOT / "artifacts" / "threshold_results.json"
```

As with Task 5 Step 5, `parents[2]` is correct after the Task 7 move. Do this edit in Task 7.

- [ ] **Step 4: Flatten the plans directory**

```bash
mkdir -p docs/plans
git mv docs/superpowers/plans/2025-07-29-coveo-atomic-pokedex-frontend.md docs/plans/
git mv docs/superpowers/plans/2026-08-29-repo-reorganization.md docs/plans/
rmdir -p docs/superpowers/plans 2>/dev/null || true
```

- [ ] **Step 5: Update `.gitignore`**

Replace the `mlruns/` entry with the `artifacts/` entry added in Task 1 (which already covers `artifacts/mlruns/` and `artifacts/threshold_results.json`).

- [ ] **Step 6: Verify and commit**

```bash
.venv/bin/python -m pytest tests/e2e -v
git add -A
git commit -m "chore: move design mockup to docs/, generated output to artifacts/"
```

---

## Task 7: Move one-off scripts under `scripts/`

**Files:**
- Move: `legacy_experiments/pokemon_db.py` → `scripts/ingest/scrape_pokedex.py`
- Move: `legacy_experiments/pokemon_db_image_scraper.py` → `scripts/ingest/scrape_images.py`
- Move: `debug_encoder.py` → `scripts/coveo/debug_encoder.py`
- Move: `check_qre_override.py` → `scripts/coveo/check_qre_override.py`
- Move: `tune_cosine_threshold.py` → `scripts/coveo/tune_cosine_threshold.py`
- Move: `test_semantic_encoder.py` → `scripts/coveo/semantic_encoder_report.py`
- Move: `probe_crga.py` → `scripts/coveo/probe_crga.py`
- Delete: `probe_crga2.py` (merged into `probe_crga.py`)
- Move: `eval_llm_comparison.py` → `scripts/mlflow/compare_llms.py`
- Move: `eval_ollama_baseline.py` → `scripts/mlflow/ollama_baseline.py`
- Delete: `legacy_experiments/` (now empty)

**Interfaces:**
- Produces: `scripts/` — everything runnable that is not the app, the harness, or a test. Each subdirectory answers one question: `ingest/` = "where did the data come from", `coveo/` = "is the index behaving", `mlflow/` = "which model answers better".

- [ ] **Step 1: Move the ingestion scrapers**

```bash
mkdir -p scripts/ingest scripts/coveo scripts/mlflow
git mv legacy_experiments/pokemon_db.py scripts/ingest/scrape_pokedex.py
git mv legacy_experiments/pokemon_db_image_scraper.py scripts/ingest/scrape_images.py
```

**Do not `rmdir legacy_experiments`.** Commit `30ee8d3` moved the old classic-UI
e2e script into it as `test_e2e_pokedex_OLD_index_page.py`, so the directory is
not empty. Task 12 removes that last file and the directory.

Both scrapers write with relative paths. Add to the top of each, and replace every bare relative output path with a path built from it:

```python
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_OUT   = REPO_ROOT / "data" / "pokemon_db.csv"
IMG_OUT   = REPO_ROOT / "data" / "images"
```

Read each script's write sites and repoint them; do not assume there is only one.

- [ ] **Step 2: Merge the two CRGA probes**

`probe_crga.py` (122 lines) takes a query from `sys.argv[1]`; `probe_crga2.py` (117 lines) loops a hardcoded three-query list. Same flow, same SSE parsing. Keep `probe_crga.py` and give it the loop:

```python
DEFAULT_QUERIES = [
    "What type is Pikachu?",
    "How does Eevee evolve into Jolteon?",
    "What is Mewtwo known for?",
]
QUERIES = sys.argv[1:] or DEFAULT_QUERIES
```

Then wrap the existing single-query body in `for QUERY in QUERIES:`. Delete `probe_crga2.py`.

- [ ] **Step 3: Move the Coveo diagnostics**

```bash
git mv probe_crga.py scripts/coveo/probe_crga.py
git rm probe_crga2.py
git mv debug_encoder.py scripts/coveo/debug_encoder.py
git mv check_qre_override.py scripts/coveo/check_qre_override.py
git mv tune_cosine_threshold.py scripts/coveo/tune_cosine_threshold.py
git mv test_semantic_encoder.py scripts/coveo/semantic_encoder_report.py
```

`test_semantic_encoder.py` is renamed because it is not a test — it is a 211-line report generator that prints a scoring table. Its `test_*` name is the reason pytest tries to collect it. Update its module docstring's first line accordingly.

- [ ] **Step 4: Move the MLflow scripts and fix their data paths**

```bash
git mv eval_llm_comparison.py scripts/mlflow/compare_llms.py
git mv eval_ollama_baseline.py scripts/mlflow/ollama_baseline.py
```

Now apply the deferred edits from Task 5 Step 5 and Task 6 Step 3 — `parents[2]` resolves correctly from `scripts/<sub>/<file>.py`:

```python
REPO_ROOT = Path(__file__).resolve().parents[2]
```

In `compare_llms.py`: `DEFAULT_CASES_FILE = REPO_ROOT / "data" / "eval_cases" / "core.json"`.
In `ollama_baseline.py`: `CASES_FILE = REPO_ROOT / "data" / "eval_cases" / "core.json"`.
In `tune_cosine_threshold.py`: `RESULTS_FILE = REPO_ROOT / "artifacts" / "threshold_results.json"`.

Also update `compare_llms.py`'s usage docstring (lines ~17-32), which still says `.venv/bin/python eval_llm_comparison.py`.

- [ ] **Step 5: Smoke-run one script from each group**

```bash
.venv/bin/python scripts/coveo/probe_crga.py "What type is Pikachu?"
.venv/bin/python -c "
from pathlib import Path
import json
p = Path('data/eval_cases/core.json')
print(p, len(json.loads(p.read_text())), 'cases')"
```

Expected: the probe streams an answer; the cases file loads 411 records. Do **not** run the scrapers — they hit pokemondb.net for 1000+ pages and would take ~30 minutes.

- [ ] **Step 6: Verify and commit**

```bash
.venv/bin/python -m pytest tests/e2e -v
git add -A
git commit -m "refactor: move one-off scripts under scripts/{ingest,coveo,mlflow}

Renames test_semantic_encoder.py to semantic_encoder_report.py - it is a
report generator, and its test_ prefix was making pytest collect it.
Merges probe_crga2.py into probe_crga.py (same flow, different query source)."
```

---

## Task 8: Split the frontend into `dashboard`, `classic` and `modules`

**Files:**
- Move: `frontend/index.html`, `pokedex-styles.css`, `pokedex-atomic.js`, `test-chrome.html` → `frontend/classic/`
- Move: `frontend/type-colors.js` → `frontend/modules/type-colors.js`
- Modify: `app.py` (`index` route), `frontend/classic/index.html`, `frontend/classic/pokedex-atomic.js`, `frontend/dashboard.js`

**Interfaces:**
- Produces: `frontend/classic/` as a self-contained legacy UI, `frontend/modules/` as the shared-module home used by Task 11.
- The `/frontend/<path:filename>` route already accepts subpaths, so no route change is needed — only the `href`/`src`/`import` strings inside the HTML and JS.

- [ ] **Step 1: Move the classic UI**

```bash
mkdir -p frontend/classic frontend/modules
git mv frontend/index.html      frontend/classic/index.html
git mv frontend/pokedex-styles.css frontend/classic/pokedex-styles.css
git mv frontend/pokedex-atomic.js  frontend/classic/pokedex-atomic.js
git mv frontend/test-chrome.html   frontend/classic/test-chrome.html
git mv frontend/type-colors.js     frontend/modules/type-colors.js
```

- [ ] **Step 2: Update the three references inside `frontend/classic/index.html`**

```
line 7:   /frontend/pokedex-styles.css  →  /frontend/classic/pokedex-styles.css
line 217: /frontend/pokedex-atomic.js   →  /frontend/classic/pokedex-atomic.js
```

`test-chrome.html:7` uses a **relative** `href="pokedex-styles.css"`, which still resolves correctly after the move — leave it.

- [ ] **Step 3: Update the two `type-colors.js` importers**

`frontend/classic/pokedex-atomic.js:1`:

```javascript
import { TYPE_COLORS } from '../modules/type-colors.js';
```

`frontend/dashboard.js:9`:

```javascript
import { TYPE_COLORS } from './modules/type-colors.js';
```

- [ ] **Step 4: Update the `index` route in `app.py`**

```python
html = (FRONTEND_DIR / "index.html").read_text()
```

becomes:

```python
html = (FRONTEND_DIR / "classic" / "index.html").read_text()
```

- [ ] **Step 5: Verify BOTH UIs load, not just the dashboard**

```bash
.venv/bin/python -m pytest tests/e2e -v
```

`test_classic_ui_still_serves` from Task 3 is the check that matters here — a broken relative import in the classic UI would otherwise go unnoticed for months. Additionally open `http://127.0.0.1:5003/` in a browser and confirm the red device chrome renders and the search box returns results. A 200 response does not prove the ES module graph resolved.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: isolate the classic device UI under frontend/classic/"
```

---

## Task 9: Create the `pokedex` package with unified config

**Files:**
- Create: `pokedex/__init__.py`, `pokedex/__main__.py`, `pokedex/config.py`
- Create: `tests/unit/test_config.py`
- Move: `app.py` → `pokedex/app.py`, `agent.py` → `pokedex/agent.py`

**Interfaces:**
- Produces:
  - `pokedex.config.settings` — a frozen dataclass instance with fields `coveo_org: str`, `coveo_token: str`, `coveo_base: str`, `coveo_pipeline: str`, `coveo_rga_pipeline: str`, `coveo_search_hub: str`, `ollama_base_url: str`, `ollama_model: str`, `port: int`, `frontend_dir: Path`, `images_dir: Path`, `repo_root: Path`.
  - `pokedex.config.app_url() -> str` returning `os.getenv("POKEDEX_URL", f"http://127.0.0.1:{settings.port}")`.
- Consumed by: Tasks 10, 11, and `eval_harness/cli.py` in Task 13.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_config.py`:

```python
from pathlib import Path


def test_coveo_base_uses_org_subdomain(monkeypatch):
    monkeypatch.setenv("COVEO_ORGANIZATION_ID", "myorg")
    from pokedex.config import load_settings
    s = load_settings()
    assert s.coveo_base == "https://myorg.org.coveo.com"


def test_coveo_base_falls_back_without_org(monkeypatch):
    monkeypatch.delenv("COVEO_ORGANIZATION_ID", raising=False)
    from pokedex.config import load_settings
    s = load_settings()
    assert s.coveo_base == "https://platform.cloud.coveo.com"


def test_rga_pipeline_falls_back_to_pipeline(monkeypatch):
    monkeypatch.delenv("COVEO_RGA_PIPELINE", raising=False)
    monkeypatch.setenv("COVEO_PIPELINE", "custom")
    from pokedex.config import load_settings
    assert load_settings().coveo_rga_pipeline == "custom"


def test_paths_resolve_to_real_directories():
    from pokedex.config import settings
    assert settings.frontend_dir.is_dir()
    assert settings.images_dir.is_dir()
    assert (settings.repo_root / "pyproject.toml").is_file()


def test_port_is_5003():
    from pokedex.config import settings
    assert settings.port == 5003
```

The fallback chain in `test_rga_pipeline_falls_back_to_pipeline` reproduces `app.py:134-135` exactly — `COVEO_RGA_PIPELINE` falling back to `COVEO_PIPELINE` falling back to `"default"`. Preserving it is not optional.

- [ ] **Step 2: Run the test and watch it fail**

Run: `.venv/bin/python -m pytest tests/unit/test_config.py -v`
Expected: `ModuleNotFoundError: No module named 'pokedex'`

- [ ] **Step 3: Write `pokedex/config.py`**

```python
"""The single definition of where things live and how to reach them.

Every port, base URL, pipeline name and directory in this project is defined
here exactly once. Before this module they were copied across nine files.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]

# macOS Monterey+ reserves port 5000 for AirPlay Receiver.
DEFAULT_PORT = 5003


@dataclass(frozen=True)
class Settings:
    coveo_org: str
    coveo_token: str
    coveo_base: str
    coveo_pipeline: str
    coveo_rga_pipeline: str
    coveo_search_hub: str
    ollama_base_url: str
    ollama_model: str
    port: int
    repo_root: Path
    frontend_dir: Path
    images_dir: Path


def load_settings() -> Settings:
    org = os.getenv("COVEO_ORGANIZATION_ID", "")
    pipeline = os.getenv("COVEO_PIPELINE", "default")
    return Settings(
        coveo_org=org,
        coveo_token=os.getenv("COVEO_ACCESS_TOKEN", ""),
        coveo_base=(
            f"https://{org}.org.coveo.com" if org else "https://platform.cloud.coveo.com"
        ),
        coveo_pipeline=pipeline,
        coveo_rga_pipeline=os.getenv("COVEO_RGA_PIPELINE", pipeline),
        coveo_search_hub=os.getenv("COVEO_SEARCH_HUB", "PokedexUI"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3"),
        port=int(os.getenv("POKEDEX_PORT", DEFAULT_PORT)),
        repo_root=REPO_ROOT,
        frontend_dir=REPO_ROOT / "frontend",
        images_dir=REPO_ROOT / "data" / "images",
    )


settings = load_settings()


def app_url() -> str:
    """Base URL of the running app, for harnesses and tests."""
    return os.getenv("POKEDEX_URL", f"http://127.0.0.1:{settings.port}")
```

- [ ] **Step 4: Move `app.py` and `agent.py` into the package**

```bash
touch pokedex/__init__.py
git mv app.py pokedex/app.py
git mv agent.py pokedex/agent.py
```

In `pokedex/app.py`, replace the module-level constants (lines 20-24) with imports from config, and change `from agent import ...` (two occurrences, inside `rga()` and `ask()`) to `from pokedex.agent import ...`. In `pokedex/agent.py`, replace its own constants block (lines 9-16) the same way.

Because config anchors paths on `REPO_ROOT` rather than `Path(__file__).parent`, moving `app.py` one directory deeper does not break `FRONTEND_DIR` or `IMAGES_DIR` — that is the point of doing config first.

- [ ] **Step 5: Write `pokedex/__main__.py`**

```python
from pokedex.app import app
from pokedex.config import settings

if __name__ == "__main__":
    import os
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=settings.port)
```

Delete the `if __name__ == "__main__":` block at the bottom of `pokedex/app.py`.

- [ ] **Step 6: Run the tests**

```bash
.venv/bin/pip install -e .
.venv/bin/python -m pytest tests/unit/test_config.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Boot the app the new way and re-run the safety net**

```bash
.venv/bin/python -m pokedex &
.venv/bin/python -m pytest tests/e2e -v
```

Expected: 4 passed. `make run` now works.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: create pokedex package with a single config module

Port, Coveo base URL, pipeline fallbacks and asset directories were each
defined in up to nine places. pokedex/config.py is now the only definition."
```

---

## Task 10: Extract one Coveo client

**Files:**
- Create: `pokedex/coveo.py`
- Create: `tests/unit/test_coveo_client.py`
- Modify: `pokedex/app.py`, `pokedex/agent.py`

**Interfaces:**
- Produces:
  - `CoveoClient(settings: Settings = <module default>)` — settings defaults to `pokedex.config.settings`, so both `CoveoClient()` and `CoveoClient(custom)` are valid. **Ruling (pre-flight): this default is required**; the plan's later steps call it both ways.
  - `.search(query: str, *, num: int = 5, first: int = 0, extra_body: dict | None = None) -> dict` — returns the **raw** Coveo response body (callers pick `results` / `totalCount` / `extendedResults` themselves).
  - `.generated_answer(query: str, *, num: int = 5, attempts: int = 6) -> GeneratedAnswer` where `GeneratedAnswer` is a dataclass with `answer: str`, `citations: list[dict]`, `stream_id: str | None`, `answer_generated: bool | None`, `error: str | None`.
  - `parse_genqa_stream(lines: Iterable[bytes | str]) -> tuple[str, list[dict], str | None]` — pure function, returns `(answer, citations, error)`. Split out from the client so it is testable without network.
- Consumed by: `pokedex/app.py` (`/api/coveo-proxy`, `/api/rga-coveo`), `pokedex/agent.py`, and — in Task 13 — `eval_harness/backends.py:DirectCoveoClient`.

The SSE parser is the highest-value extraction in this plan: it currently exists four times (`app.py:189-241`, `probe_crga.py`, `probe_crga2.py`, `eval_harness/backends.py`), each with the same subtle double-`json.loads` (the outer event, then the `payload` string inside it).

- [ ] **Step 1: Write the failing test for the stream parser**

`tests/unit/test_coveo_client.py`:

```python
import json


def _event(payload_type, payload, **extra):
    return "data: " + json.dumps(
        {"payloadType": payload_type, "payload": json.dumps(payload), **extra}
    )


def test_parses_text_deltas_in_order():
    from pokedex.coveo import parse_genqa_stream
    lines = [
        _event("genqa.messageType", {"textDelta": "Pikachu is "}),
        _event("genqa.messageType", {"textDelta": "an Electric-type."}),
        _event("genqa.endOfStreamType", {}),
    ]
    answer, citations, error = parse_genqa_stream(lines)
    assert answer == "Pikachu is an Electric-type."
    assert citations == []
    assert error is None


def test_collects_citations():
    from pokedex.coveo import parse_genqa_stream
    lines = [
        _event("genqa.citationsType",
               {"citations": [{"title": "Pikachu", "clickUri": "https://x/pikachu"}]}),
        _event("genqa.endOfStreamType", {}),
    ]
    _, citations, _ = parse_genqa_stream(lines)
    assert citations[0]["title"] == "Pikachu"


def test_surfaces_error_finish_reason():
    from pokedex.coveo import parse_genqa_stream
    lines = ['data: ' + json.dumps(
        {"finishReason": "ERROR", "errorMessage": "model unavailable"})]
    answer, _, error = parse_genqa_stream(lines)
    assert error == "model unavailable"
    assert answer == ""


def test_ignores_non_data_lines_and_bad_json():
    from pokedex.coveo import parse_genqa_stream
    lines = [
        "",
        ": keep-alive",
        "data: {not json",
        _event("genqa.messageType", {"textDelta": "ok"}),
        _event("genqa.endOfStreamType", {}),
    ]
    answer, _, error = parse_genqa_stream(lines)
    assert answer == "ok"
    assert error is None


def test_accepts_bytes_lines():
    from pokedex.coveo import parse_genqa_stream
    lines = [
        _event("genqa.messageType", {"textDelta": "hi"}).encode(),
        _event("genqa.endOfStreamType", {}).encode(),
    ]
    answer, _, _ = parse_genqa_stream(lines)
    assert answer == "hi"


def test_stops_at_end_of_stream():
    from pokedex.coveo import parse_genqa_stream
    lines = [
        _event("genqa.messageType", {"textDelta": "first"}),
        _event("genqa.endOfStreamType", {}),
        _event("genqa.messageType", {"textDelta": " LEAKED"}),
    ]
    answer, _, _ = parse_genqa_stream(lines)
    assert answer == "first"
```

- [ ] **Step 2: Run and watch it fail**

Run: `.venv/bin/python -m pytest tests/unit/test_coveo_client.py -v`
Expected: `ModuleNotFoundError: No module named 'pokedex.coveo'`

- [ ] **Step 3: Write `pokedex/coveo.py`**

Port the logic verbatim from `pokedex/app.py:121-262`. Do not "improve" it — the retry count (6 attempts, 1 s apart), the `Accept: */*` header on the stream, the 15 s search timeout, the 45 s stream timeout and the `"(no answer generated)"` sentinel are all load-bearing and the eval harness grades against them.

```python
"""The one Coveo client.

Search and CRGA streaming previously lived in app.py, agent.py, three probe
scripts and eval_harness/backends.py, in five slightly-divergent copies.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Iterable

import requests

from pokedex.config import Settings, settings as default_settings


@dataclass
class GeneratedAnswer:
    answer: str = ""
    citations: list[dict] = field(default_factory=list)
    stream_id: str | None = None
    answer_generated: bool | None = None
    error: str | None = None


def parse_genqa_stream(lines: Iterable[bytes | str]) -> tuple[str, list[dict], str | None]:
    """Fold an SSE genqa.* stream into (answer, citations, error)."""
    parts: list[str] = []
    citations: list[dict] = []
    for raw in lines:
        if not raw:
            continue
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[len("data:"):].strip())
        except ValueError:
            continue
        if event.get("finishReason") == "ERROR":
            return "".join(parts), citations, event.get("errorMessage", "unknown")
        payload_raw = event.get("payload", "")
        try:
            payload = json.loads(payload_raw) if payload_raw else {}
        except ValueError:
            payload = {}
        ptype = event.get("payloadType", "")
        if ptype == "genqa.messageType":
            delta = payload.get("textDelta", "")
            if delta and delta.strip():
                parts.append(delta)
        elif ptype == "genqa.citationsType":
            citations = payload.get("citations", [])
        elif ptype == "genqa.endOfStreamType" or event.get("finishReason") == "COMPLETED":
            break
    return "".join(parts), citations, None
```

Then add the `CoveoClient` class wrapping `search()` and `generated_answer()`, both built from `self.s.coveo_base`, `self.s.coveo_token`, `self.s.coveo_search_hub` and the appropriate pipeline field.

- [ ] **Step 4: Run the parser tests**

Run: `.venv/bin/python -m pytest tests/unit/test_coveo_client.py -v`
Expected: 6 passed.

- [ ] **Step 5: Rewrite the two callers to use the client**

`pokedex/agent.py:_coveo_search` becomes a thin mapping over `CoveoClient().search(query, num=num_results)["results"]`. `pokedex/app.py:rga_coveo` becomes a call to `CoveoClient().generated_answer(query)` plus the existing JSON shaping (the `clean_citations` normalisation and the "RGA model did not trigger" fallback stay in the route, because they are HTTP-response concerns).

Keep the SSRF path allowlist (`_ALLOWED_PATH`, `app.py:70`) in the **route**, not in the client — it guards untrusted browser input, and the client is also called from trusted server-side code.

- [ ] **Step 6: Verify end to end against real Coveo**

```bash
.venv/bin/python -m pokedex &
curl -s -X POST http://127.0.0.1:5003/api/rga-coveo \
  -H 'Content-Type: application/json' \
  -d '{"query":"What type is Pikachu?"}' | head -c 500
```

Expected: a JSON body with a non-empty `answer` and a populated `citations` array. A `"(no answer generated)"` or `"(CRGA stream error: ...)"` response means the refactor changed behaviour — revert and compare against `git stash`.

- [ ] **Step 7: Run everything and commit**

```bash
.venv/bin/python -m pytest -v
git add -A
git commit -m "refactor: single Coveo client and one testable SSE parser

The genqa stream parser existed in four copies with no test coverage.
It is now one pure function with six tests."
```

---

## Task 11: Split routes into blueprints

**Files:**
- Create: `pokedex/routes/__init__.py`, `pages.py`, `coveo_api.py`, `llm_api.py`
- Create: `pokedex/ollama_client.py`
- Create: `tests/unit/test_routes.py`
- Modify: `pokedex/app.py` (becomes a ~30-line app factory)

**Interfaces:**
- Produces: `pokedex.app.create_app() -> Flask` and a module-level `app = create_app()` for backwards compatibility with `python -m pokedex`.
- Blueprints: `pages_bp` (no prefix), `coveo_bp` (`/api`), `llm_bp` (`/api`).
- `pokedex.ollama_client.chat(prompt: str, model: str | None = None) -> str` and `list_local_models() -> list[str]`.

- [ ] **Step 1: Write the failing route tests**

`tests/unit/test_routes.py`:

```python
import pytest


@pytest.fixture
def client():
    from pokedex.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_all_routes_are_registered(client):
    rules = {r.rule for r in client.application.url_map.iter_rules()}
    for expected in [
        "/", "/dashboard", "/readme",
        "/frontend/<path:filename>", "/images/<filename>",
        "/api/coveo-token", "/api/coveo-proxy",
        "/api/rga", "/api/rga-coveo", "/api/ask",
        "/api/set-model", "/api/models",
    ]:
        assert expected in rules, f"route {expected} disappeared"


def test_dashboard_renders_with_org_injected(client, monkeypatch):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert b"{{ COVEO_ORGANIZATION_ID }}" not in r.data


def test_coveo_proxy_rejects_paths_outside_search(client):
    r = client.post("/api/coveo-proxy",
                    json={"path": "/rest/organizations/x/apikeys", "body": {}})
    assert r.status_code == 400
```

The third test pins the SSRF guard added during the current hardening pass — a blueprint split is exactly the kind of change that could silently drop it.

- [ ] **Step 2: Run and watch it fail**

Run: `.venv/bin/python -m pytest tests/unit/test_routes.py -v`
Expected: `ImportError: cannot import name 'create_app'`

- [ ] **Step 3: Extract `pokedex/ollama_client.py`**

Move `generate_rga_answer`'s Ollama call out of `agent.py` and `list_models`'s client construction out of `app.py:303` into one module that owns the `ol.Client(host=settings.ollama_base_url)` instance.

- [ ] **Step 4: Create the three blueprint modules**

Move routes verbatim. `pages.py` gets `/`, `/dashboard`, `/readme`, `/frontend/<path:filename>`, `/images/<filename>`. `coveo_api.py` gets `/coveo-token`, `/coveo-proxy`, `/rga-coveo` (registered with `url_prefix="/api"`). `llm_api.py` gets `/rga`, `/ask`, `/set-model`, `/models`.

The mutable `_active_model` global in `app.py:27` moves into `llm_api.py`. Note in a comment that it is process-local module state and does not survive a restart — that is existing behaviour, do not change it here.

- [ ] **Step 5: Reduce `pokedex/app.py` to a factory**

```python
"""Flask application factory."""
from flask import Flask
from flask_cors import CORS

from pokedex.config import settings
from pokedex.routes.coveo_api import coveo_bp
from pokedex.routes.llm_api import llm_bp
from pokedex.routes.pages import pages_bp


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, origins=[f"http://127.0.0.1:{settings.port}",
                       f"http://localhost:{settings.port}"])
    app.register_blueprint(pages_bp)
    app.register_blueprint(coveo_bp, url_prefix="/api")
    app.register_blueprint(llm_bp, url_prefix="/api")
    return app


app = create_app()
```

Copy the CORS `origins` list from the current hardened `app.py:16-18` rather than the sketch above if it has diverged.

- [ ] **Step 6: Run all tests**

```bash
.venv/bin/python -m pytest tests/unit -v
.venv/bin/python -m pokedex &
.venv/bin/python -m pytest tests/e2e -v
```

Expected: all pass. `test_all_routes_are_registered` is the guard that no route was lost in the split.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: split Flask routes into pages/coveo/llm blueprints"
```

---

## Task 12: Convert the Playwright scripts into a real e2e suite

**Files:**
- Create: `tests/e2e/test_dashboard_search.py`, `tests/e2e/test_type_effectiveness.py`, `tests/e2e/test_filters_and_map.py`
- Port from: `test_dashboard_e2e.py` (primary), `test_dashboard_review.py`, `test_diag2.py`
- Delete: `test_dashboard_e2e.py`, `test_dashboard_review.py`, `test_diag2.py`, `test_search.py`, `legacy_experiments/test_e2e_pokedex_OLD_index_page.py`, and the now-empty `legacy_experiments/`

**Interfaces:**
- Consumes: `dashboard`, `browser`, `live_url` fixtures from Task 2.
- Produces: `make test-e2e` as the real regression gate for the UI.

**Ruling (pre-flight): `test_dashboard_e2e.py` is the primary conversion source.**
Commit `30ee8d3` added it (230 lines) after this plan was written. It targets
`/dashboard`, carries an `EXPECTED_WEAKNESSES` table derived from the Gen VI+
chart, and its docstring records that the file it replaced was asserting on
selectors that do not exist on the dashboard — so it passed 11/11 while the
shipped page went untested. Port it first, then fold in only what the older
scripts cover and it does not.

`test_dashboard_review.py` (611 lines) and `test_diag2.py` (449 lines) between
them hold roughly 90 behavioural assertions written as
`log(section, check, "PASS"/"FAIL")` calls that print but never fail a build.
They overlap heavily with each other and with `test_dashboard_e2e.py` — all three
check Charizard, Gengar and Snorlax weaknesses. Convert the unique ones; do not
discard an assertion without recording why.

- [ ] **Step 1: Add a search helper to `tests/e2e/conftest.py`**

Port `test_diag2.py:19-45`'s `search_and_wait`, which is the only correct wait strategy in the repo — it waits for `#rp-name` to become the expected name rather than sleeping:

```python
@pytest.fixture
def search(dashboard):
    def _search(query: str, expect: str | None = None, timeout: int = 20000):
        dashboard.fill("#search-input", query)
        dashboard.press("#search-input", "Enter")
        if expect:
            dashboard.wait_for_function(
                "(name) => document.querySelector('#rp-name')"
                "?.textContent.includes(name)",
                arg=expect, timeout=timeout,
            )
        else:
            dashboard.wait_for_load_state("networkidle", timeout=timeout)
        return dashboard
    return _search
```

- [ ] **Step 2: Write `tests/e2e/test_type_effectiveness.py`**

Convert the highest-value assertions — these encode real Pokémon rules and would catch a genuine regression in `dashboard.js:typeMultiplier`:

```python
import pytest

pytestmark = pytest.mark.e2e


def _weak(page):
    return page.locator("#weak-chips").inner_html()


def test_charizard_has_quadruple_rock_weakness(search):
    page = search("Charizard", expect="Charizard")
    html = _weak(page)
    assert "Rock" in html and "×4" in html


def test_dragonite_has_quadruple_ice_weakness(search):
    page = search("Dragonite", expect="Dragonite")
    html = _weak(page)
    assert "Ice" in html and "×4" in html


def test_gyarados_has_quadruple_electric_weakness(search):
    page = search("Gyarados", expect="Gyarados")
    html = _weak(page)
    assert "Electric" in html and "×4" in html


def test_gengar_is_immune_to_normal_and_fighting(search):
    page = search("Gengar", expect="Gengar")
    html = _weak(page)
    assert "Ghost" in html and "Dark" in html and "Ground" in html
    assert "Fighting" not in html
    assert "Normal" not in html


def test_steelix_is_immune_to_poison(search):
    page = search("Steelix", expect="Steelix")
    assert "Poison" not in _weak(page)


def test_snorlax_only_weakness_is_fighting(search):
    page = search("Snorlax", expect="Snorlax")
    html = _weak(page)
    assert "Fighting" in html
    assert "Water" not in html and "Fire" not in html
```

- [ ] **Step 3: Write `tests/e2e/test_dashboard_search.py`**

Convert `test_dashboard_review.py:196-310` — the no-results path, the blank search, result-row click, and the similar-Pokémon grid:

```python
import pytest

pytestmark = pytest.mark.e2e


def test_nonsense_query_does_not_crash(search):
    page = search("zzzznotapokemon")
    assert page.locator("#results-list").count() == 1
    assert page.locator("#rp-name").inner_text() != ""


def test_clicking_a_result_row_updates_the_right_panel(search):
    page = search("fire", expect=None)
    page.wait_for_selector("#results-list .ritem", timeout=15000)
    rows = page.locator("#results-list .ritem")
    if rows.count() < 2:
        pytest.skip("need at least two results to test row selection")
    before = page.locator("#rp-name").inner_text()
    rows.nth(1).click()
    page.wait_for_function(
        "(prev) => document.querySelector('#rp-name')?.textContent.trim() !== prev",
        arg=before, timeout=15000,
    )
    assert page.locator("#results-list .ritem.sel").count() == 1


def test_similar_grid_excludes_the_current_pokemon(search):
    page = search("Pikachu", expect="Pikachu")
    page.wait_for_selector("#similar-grid .simcard", timeout=20000)
    names = page.locator("#similar-grid .simcard").all_inner_texts()
    assert names
    assert not any("Pikachu" in n for n in names)
```

- [ ] **Step 4: Write `tests/e2e/test_filters_and_map.py`**

Convert `test_dashboard_review.py:225-360` — type chip toggle on/off, generation row toggle, map gen toggles being mutually exclusive, and map pan updating `data-pan-x`.

- [ ] **Step 5: Run the suite and triage honestly**

```bash
.venv/bin/python -m pokedex &
.venv/bin/python -m pytest tests/e2e -v
```

Some of these will fail — `test_diag2.py:238` already flags a known Ground-immunity bug (`BUG-GroundImmunity`) and `test_diag2.py:86` notes a Charizard Ground simplification. **Do not fix app behaviour in this task.** For each genuine failure: mark it `@pytest.mark.xfail(reason="...", strict=True)` and add an entry to `docs/known-issues.md` describing the wrong behaviour and the correct one. A strict xfail turns green the day the bug is fixed and turns red if it is fixed by accident and forgotten.

- [ ] **Step 6: Delete the superseded scripts**

```bash
git rm test_search.py legacy_experiments/test_e2e_pokedex_OLD_index_page.py
rm -f test_dashboard_e2e.py test_dashboard_review.py test_diag2.py
rmdir legacy_experiments
```

`legacy_experiments/` is empty at this point — Task 7 moved both scrapers out and
deliberately left the directory standing for this step.

`test_e2e_pokedex_OLD_index_page.py` (192 lines) and `test_search.py` (109 lines)
target the **classic** UI at `/`, and `30ee8d3` already marked the first as
superseded. Before deleting, check whether either asserts something the new suite
does not cover; `test_search.py`'s trick of driving the Atomic headless
controller through the shadow root (`sb.searchBox.updateText(q); sb.searchBox.submit()`)
is worth preserving as a helper in `tests/e2e/conftest.py` if the classic UI is
to stay tested.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "test: convert playwright scripts into a real e2e suite

~90 assertions previously printed PASS/FAIL without ever failing a build.
Known-bad behaviours are recorded as strict xfails, not silently dropped."
```

---

## Task 13: Point the eval harness at shared config and add the type-chart parity test

**Files:**
- Modify: `eval_harness/cli.py:23-25,58`, `eval_harness/backends.py:161`
- Create: `tests/unit/test_type_chart_parity.py`
- Create: `frontend/modules/type-chart.js`
- Modify: `frontend/dashboard.js`

**Interfaces:**
- Consumes: `pokedex.config.settings`, `pokedex.config.app_url()` from Task 9; `pokedex.coveo.parse_genqa_stream` from Task 10.
- Produces: `frontend/modules/type-chart.js` exporting `TYPE_CHART` and `typeMultiplier(atk, defTypes)`.

- [ ] **Step 1: Repoint the harness at shared config**

In `eval_harness/cli.py`, replace:

```python
ROOT = Path(__file__).parent.parent
DATA = ROOT / "eval_data"
```

with:

```python
from pokedex.config import app_url, settings
DATA = settings.repo_root / "eval_data"
```

and line 58's default:

```python
r.add_argument("--app", default=app_url())
```

In `eval_harness/backends.py:161`, `DirectCoveoClient.__init__` builds its own base URL — replace with `settings.coveo_base`, and replace its inline SSE parsing with `parse_genqa_stream`. Keep `DirectCoveoClient`'s `answer_generated` extraction, which is the thing it exists for and which `parse_genqa_stream` does not return.

- [ ] **Step 2: Verify the harness still runs against stored data**

```bash
.venv/bin/python -m eval_harness runs
.venv/bin/python -m eval_harness report
.venv/bin/python -m eval_harness regrade --run 1
```

`regrade` re-scores stored answers without re-querying, so it exercises the store, grader and reference renderer with no network. Expected: the same scoreboard as before the change. If the numbers move, the refactor changed grading — revert.

- [ ] **Step 3: Extract the JS type chart into a module**

Move `TYPE_CHART`, `ALL_TYPES`, `typeMultiplier` and `multLabel` from `frontend/dashboard.js:19-63` into `frontend/modules/type-chart.js`, export them, and import in `dashboard.js`:

```javascript
import { TYPE_CHART, ALL_TYPES, typeMultiplier, multLabel } from './modules/type-chart.js';
```

- [ ] **Step 4: Write the parity test**

`tests/unit/test_type_chart_parity.py` — this is the test that stops the UI and the grader from silently disagreeing:

```python
import re
from pathlib import Path

from pokedex.config import settings
from eval_harness.typechart import TYPES, TypeChart

JS = settings.repo_root / "frontend" / "modules" / "type-chart.js"


def _parse_js_chart() -> dict[str, dict[str, float]]:
    """Read the sparse TYPE_CHART object literal out of the ES module."""
    src = JS.read_text()
    body = src.split("const TYPE_CHART = {", 1)[1].split("\n};", 1)[0]
    chart: dict[str, dict[str, float]] = {}
    for line in body.splitlines():
        m = re.match(r"\s*(\w+):\s*\{(.*)\},?\s*$", line)
        if not m:
            continue
        atk, pairs = m.group(1), m.group(2)
        chart[atk] = {
            k: float(v)
            for k, v in re.findall(r"(\w+)\s*:\s*([\d.]+)", pairs)
        }
    return chart


def test_js_and_python_cover_the_same_18_types():
    js = _parse_js_chart()
    assert set(js) == set(TYPES)


def test_js_chart_matches_python_chart():
    js = _parse_js_chart()
    mismatches = []
    for atk in TYPES:
        for dfn in TYPES:
            js_mult = js[atk].get(dfn, 1.0)
            py_mult = TypeChart.effectiveness(atk, [dfn])
            if js_mult != py_mult:
                mismatches.append(f"{atk} -> {dfn}: js={js_mult} py={py_mult}")
    assert not mismatches, "\n".join(mismatches)
```

`TypeChart.effectiveness(attack_type, defender_types) -> float` is a **staticmethod**
(`eval_harness/typechart.py:105`), so the test needs no instance and therefore no
PokeAPI cache path. `TYPES` is the module-level list of all 18 type names
(`typechart.py:16`).

- [ ] **Step 5: Run the parity test**

Run: `.venv/bin/python -m pytest tests/unit/test_type_chart_parity.py -v`

If it fails, one of the two charts is wrong. Determine which by checking a disputed pair against PokéAPI, fix the wrong one, and record the finding in the commit message — a real discrepancy here means the app has been showing wrong weaknesses or the grader has been marking correct answers wrong.

- [ ] **Step 6: Run everything and commit**

```bash
.venv/bin/python -m pytest -v
git add -A
git commit -m "refactor: harness reads shared config; add JS/Python type-chart parity test"
```

---

## Task 14: Documentation — README, architecture, and the harness's first commit

**Files:**
- Rewrite: `README.md`
- Create: `docs/architecture.md`
- Modify: `frontend/readme.html` (the file table and the file paths it names)
- Modify: `eval_harness/README.md` (the `../app.py` link)
- Add: `eval_harness/` and `eval_data/` to git

- [ ] **Step 1: Confirm the eval harness survived the reorganization**

The harness came in via the Task 0 merge (`d4b20bf`). Verify it is tracked, intact, and that its generated data is still ignored:

```bash
git ls-files eval_harness eval_data
```

Expected: 13 `eval_harness/*` entries plus `eval_data/corpus.json` and `eval_data/type_cache.json` — and **not** `eval_data/pokedex_eval.db` or anything under `eval_data/exports/`. If the `.db` is tracked, the `.gitignore` merge in Task 0 Step 3 dropped a rule; restore it and `git rm --cached` the database.

Once merged and reorganized, delete the now-redundant `data-gathering-eval-harness` branch:

```bash
git branch -d data-gathering-eval-harness
```

- [ ] **Step 2: Rewrite `README.md`**

The current README is three lines pointing at an image and an in-app URL. It needs to stand on its own for someone landing on the public GitHub page. Cover, in order: one-paragraph what-it-is; a screenshot (`docs/readme-preview.png` already exists); Quick start (clone → `pip install -r requirements-dev.txt` → `cp .env.example .env` → fill Coveo creds → `make run` → open `/dashboard`); a repository-map table with one line per top-level directory; how to run the eval harness; and a pointer to `docs/architecture.md` and to the styled `/readme` page.

- [ ] **Step 3: Write `docs/architecture.md`**

Document the things that are currently only discoverable by reading source:

- **Request flow for a search:** browser → Atomic headless engine → `/api/coveo-proxy` (server injects the bearer token; `_ALLOWED_PATH` restricts it to `/rest/search/v2*`) → Coveo → results rendered by `dashboard.js:renderResultsList`.
- **The two RGA paths:** `/api/rga-coveo` (Coveo CRGA — search for a `generativeQuestionAnsweringId`, then consume an SSE stream, retried up to 6× at 1 s because the stream ID is not always ready on the first search) versus `/api/rga` (local Ollama over the top-5 excerpts). The model dropdown picks between them.
- **Why the browser never sees the Coveo key**, and what `/api/coveo-token` does return.
- **Where Pokémon data comes from:** `data/pokemon_db.csv` was scraped by `scripts/ingest/scrape_pokedex.py` and indexed into Coveo; artwork by `scripts/ingest/scrape_images.py` into `data/images/`; live stats, moves and encounter locations come from PokéAPI **at runtime in the browser**, not from the index.
- **The Semantic-PokEncoder:** a KNN ranking function attached to the Coveo `default` pipeline; it fires automatically, which is why no `mlParameters` appear in any request body (`agent.py:34-35`).
- **The type chart lives twice** (JS for the UI, Python for the grader) and is held in sync by `tests/unit/test_type_chart_parity.py`.
- **Two UIs:** `/dashboard` is primary; `/` is the original device-shaped UI, kept working.

- [ ] **Step 4: Fix every stale path in `frontend/readme.html`**

Its file table (lines ~449-456) still names `frontend/index.html`, `frontend/pokedex-atomic.js`, `frontend/pokedex-styles.css`, `frontend/result-template.js`, and line 484 still says artwork comes from `pokemon_images/`. Update to the new paths, and delete the `result-template.js` row.

- [ ] **Step 5: Fix the harness README's cross-link**

`eval_harness/README.md` links `[app.py](../app.py)`; it is now `[app.py](../pokedex/app.py)`. Also update the quick-start line `python app.py` to `make run`.

- [ ] **Step 6: Final verification**

```bash
.venv/bin/python -m pytest -v
.venv/bin/python -m pokedex &
.venv/bin/python -m eval_harness report
```

Then open and click through all three pages: `/dashboard`, `/`, `/readme`.

- [ ] **Step 7: Confirm the root is clean**

```bash
ls -1 | grep -v '^\.'
```

Expected exactly: `Makefile`, `README.md`, `artifacts`, `data`, `docs`, `eval_data`, `eval_harness`, `frontend`, `pokedex`, `pyproject.toml`, `requirements-dev.txt`, `scripts`, `tests`. Anything else is an escapee — place it or delete it.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "docs: rewrite README, add architecture doc, fix stale paths"
```

---

## Verification Checklist

Run this after Task 14. Every line must pass before the branch merges.

```bash
# 1. The root holds only directories and manifests
ls -1 | grep -v '^\.'

# 2. Every test passes
.venv/bin/python -m pytest -v

# 3. The app boots from the documented entry point
make run &

# 4. All three pages serve
curl -sf -o /dev/null -w '%{http_code} /\n'          http://127.0.0.1:5003/
curl -sf -o /dev/null -w '%{http_code} /dashboard\n' http://127.0.0.1:5003/dashboard
curl -sf -o /dev/null -w '%{http_code} /readme\n'    http://127.0.0.1:5003/readme

# 5. Both RGA paths answer
curl -sf -X POST http://127.0.0.1:5003/api/rga-coveo \
  -H 'Content-Type: application/json' -d '{"query":"What type is Pikachu?"}'

# 6. The harness still reads its history
.venv/bin/python -m eval_harness runs
.venv/bin/python -m eval_harness regrade --run 1

# 7. Nothing that should be ignored is tracked
git ls-files | grep -E 'artifacts/|\.db$|data/images/(?!placeholder)' || echo "clean"

# 8. No stale path references survive
grep -rn "pokemon_images\|legacy_experiments\|result-template\|eval_cases.json" \
  --include="*.py" --include="*.js" --include="*.html" --include="*.md" . \
  | grep -v '\.venv' | grep -v 'docs/plans/'
```

Line 8 should return nothing outside `docs/plans/` (historical plans may legitimately mention old paths).

---

## Risk Register

| Risk | Where it bites | Mitigation |
|---|---|---|
| A moved asset 404s only in the browser, not in a `curl` | Task 5 (`/images/`), Task 8 (`frontend/classic/`) | Task 3's smoke test fetches a real asset; Task 8 Step 5 additionally requires a human to open `/` and confirm the ES module graph resolved |
| The CRGA refactor silently degrades answers | Task 10 | Six parser unit tests plus a live `curl` against `/api/rga-coveo`; `eval_harness regrade` in Task 13 compares scoreboards before and after |
| A route is dropped during the blueprint split | Task 11 | `test_all_routes_are_registered` asserts all twelve rules by exact string |
| The SSRF guard is lost in the split | Task 11 | `test_coveo_proxy_rejects_paths_outside_search` |
| The in-flight hardening work on `app.py` conflicts with Task 9's move | Task 9 | Land all in-flight fixes on `app.py` and merge them **before** starting Task 9; the plan deliberately puts the `app.py` move ninth for this reason |
| Work continues on `data-gathering-eval-harness` after the merge, re-splitting the tree | Task 0 | Delete the branch in Task 14 Step 1; do all further harness work on the merged branch |
| `git log --follow` breaks for moved files | Tasks 5–9 | Never mix a move and a content edit in one commit; the tasks are ordered so moves land first, edits second |
| Converting the Playwright scripts hides a real bug | Task 12 | Genuine failures become `strict=True` xfails plus a `docs/known-issues.md` entry — never a deleted assertion |

---

## Deferred — Not In This Plan

These are real improvements that would each need their own plan. Recording them here so they are not silently lost:

1. **Splitting `frontend/dashboard.js` (1441 lines) into the nine modules** sketched in the target structure. Task 13 extracts only `type-chart.js`, because that one has a correctness test to justify it. The rest is a large, purely-mechanical JS refactor with no test harness behind it yet — do it after Task 12's e2e suite exists to catch regressions.
2. **Removing the duplicated PokéAPI client** — `dashboard.js:242` and `pokedex-atomic.js:74` both implement `fetchPokeData` with their own caches.
3. **Retiring the classic UI at `/`.** It is a maintenance cost with no traffic. Deleting it is a product decision, not a cleanup.
4. **Making `_active_model` per-session rather than a process global** — it currently means two browsers on the same server fight over the model selector.
5. **CI.** With `pyproject.toml` and a real `tests/` tree in place, a GitHub Actions workflow running `pytest tests/unit` on every push becomes a ten-line file. The e2e tests need a live Coveo org, so they stay manual or gated on a repository secret.
6. **Pruning the nine stale local branches** (`dashboard-tweak-with-evolutions`, `front-end-redesign`, `make-it-a-pokedex`, `make-search-retrieve-pokemon`, `make-search-work-raw`, `map-fixed`, `remove-pokeapi`, `steam-deck-decky-compatibility`, `working-search-box`) once this branch merges to `main`.
