# Agentic Pokédex

A Pokédex backed by Coveo search, Coveo Relevance Generative Answering (CRGA), and a local Ollama fallback. Ask about Pokémon matchups in natural language and get grounded answers with citations, type-effectiveness chips, and encounter maps — on a dashboard, or in a multi-turn conversation with Professor Oak that remembers what you just asked and checks his own type claims before answering.

![Agentic Pokédex dashboard](docs/readme-preview.png)

> **Styled README** — available at [`/readme`](http://127.0.0.1:5003/readme) when the app is running. The image above is a screenshot of that page.

---

## Quick start

```bash
git clone <repo>
cd <repo>
pip install -r requirements-dev.txt
cp .env.example .env          # fill in your Coveo + Ollama credentials
make run                      # starts on http://127.0.0.1:5003
open http://127.0.0.1:5003/dashboard
```

---

## The three surfaces

| Route | What it is |
|---|---|
| `/dashboard` | The primary UI. 3-column dark dashboard — type and generation facets, base stats, moves, type effectiveness, encounter map, similar-Pokémon grid, and a per-row **Compare** button that hands off to the coach |
| `/coach` | Multi-turn chat with Professor Oak. Session memory, side-by-side comparison panels, Coveo query suggestions, challenge mode, and inline type-error flags |
| `/` | The original Pokédex-device-shaped UI (red chrome, screen bezel, control row), served from `frontend/classic/` |

---

## The Pokémon Coach

`/coach` is a conversation, not a search box. One turn goes through:

1. **The question**, typed against live Coveo query suggestions.
2. **History folded in** — the last 4 turns are prepended so pronouns resolve. Oak's previous replies are truncated to 200 characters so they don't crowd out the new question, and the canonical Pokémon names from each turn ride along, so "who counters *it*?" works even when the original message was misspelled.
3. **Comparison intent detection** — four regex patterns catch `X vs Y`, `compare X and Y`, `between X and Y`, and `X or Y`.
4. **Coveo CRGA** answers with citations. If the model abstains, the coach says so and falls back to the top search excerpts rather than inventing a reply.
5. **Grading** — the same grader the eval harness uses checks the answer's type and chart claims. Mismatches surface as `⚠ Type error` flags under the bubble instead of passing silently.
6. **Rendering** — a bubble with citation pills, plus a dual comparison panel (artwork, stats, weaknesses, resistances, moves, a `ΔBST` delta column and a verdict bar) when a comparison was detected.

The 🎲 **Challenge me** chip draws a real scenario from the eval harness — a team of six and a wild Pokémon on a chosen difficulty axis — and opens the conversation with it. Sessions are in-memory: 20 turns each, 1 000 sessions max with LRU eviction, cleared on restart.

---

## Repository map

| Directory / file | Contents |
|---|---|
| `pokedex/` | Flask application package — `app.py` (factory), `config.py` (settings), `coveo.py` (CoveoClient + SSE parser), `agent.py` (Ollama RAG loop), `conversation.py` (in-memory session store), `ollama_client.py`, `routes/` (`pages`, `coach_api`, `coveo_api`, `llm_api`) |
| `frontend/` | Browser-side assets — `dashboard.js/.html/.css`, `coach.js/.html/.css`, `classic/` (original device UI), `modules/` (pokemon-panel.js, type-colors.js, type-chart.js), `readme.html` (the styled README) |
| `tests/` | `unit/` (31 tests, pytest, no server needed), `e2e/` (23 tests, Playwright against a live server) |
| `eval_harness/` | Repeatable wild-encounter evaluation — draws scenarios from the live Coveo index, grades answers against a type chart, stores everything in SQLite |
| `eval_data/` | `corpus.json` + `type_cache.json` (committed); `pokedex_eval.db` (gitignored, regenerable) |
| `scripts/` | `ingest/` (one-off scraper for Pokémon DB + artwork), `coveo/` (CRGA probe scripts), `mlflow/` (LLM comparison) |
| `data/` | `pokemon_db.csv` (scraped Pokédex), `images/` (artwork) |
| `docs/` | `architecture.md`, `known-issues.md`, `plans/`, `readme-preview.png` |
| `artifacts/` | Generated outputs (gitignored) |

---

## API routes

| Method | Route | Description |
|---|---|---|
| `POST` | `/api/coach` | One coach turn. `{session_id, message}` → `{answer, citations, comparison, grading_flags}` |
| `POST` | `/api/coach-challenge` | Draws an eval-harness battle scenario. `{axis?}` → `{prompt, session_id, scenario}` |
| `GET` | `/api/coveo-token` | `{token, organizationId}` — the API key is injected server-side, never baked into HTML/JS |
| `POST` | `/api/coveo-proxy` | Proxies Coveo REST. Path is regex-anchored to `/rest/search/v2*` |
| `POST` | `/api/rga-coveo` | Coveo CRGA (Professor Oak) → `{answer, citations}` |
| `POST` | `/api/rga` | Ollama RGA. `{query, context[]}` → `{answer}` |
| `POST` | `/api/ask` | Full agentic loop. `{query}` → `{message, pokemon_list}` |
| `POST` | `/api/set-model` | Hot-swaps the active Ollama model |
| `GET` | `/api/models` | Lists locally pulled Ollama models |
| `GET` | `/api/pokemon-correct` | `?q=<name>` → closest known Pokémon name within 2 edits, or `null`. Used to retry PokéAPI lookups after a 404 |

---

## Running the tests

```bash
make test-unit    # 31 unit tests — no server needed
make run &        # start the server
make test-e2e     # 23 Playwright e2e tests against the running server
```

Observed defects are recorded as strict xfails and documented in [`docs/known-issues.md`](docs/known-issues.md), so a fix trips the suite rather than passing unnoticed.

---

## Running the eval harness

```bash
make run &                                    # start the app
python -m eval_harness run --label baseline   # run an evaluation
python -m eval_harness report                 # scoreboard
python -m eval_harness regrade --run 1        # re-score stored answers
```

See [`eval_harness/README.md`](eval_harness/README.md) for full documentation.

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for a detailed walkthrough of the request flow, the two RGA paths, how Pokémon data is sourced, and the Semantic-PokEncoder.
