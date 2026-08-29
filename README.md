# Agentic Pokédex

> **Agentic Edition — Dark Dashboard**
> Coveo-powered search · Generative Answering · Ollama local LLM

A full-stack Pokédex powered by **Coveo Atomic** for enterprise-grade search and a local **Ollama LLM** for on-device generative answers — all wrapped in a slick dark 3-column dashboard. Search any Pokémon by name, type, ability, or natural language; get AI-generated insights from Professor Oak; explore habitats on regional maps; and compare similar Pokémon side-by-side. No build step. No external LLM calls in the hot path. Just Flask + Coveo + local inference.

**Stack:** Flask 2.x · Coveo Atomic v3 · Ollama · PokéAPI · Python 3.11+ · Vanilla JS (ESM)

---

## Architecture

| Layer | Technology | Role |
|---|---|---|
| Search | Coveo Atomic (CDN, headless) | Web-component search engine; proxied through Flask so API keys never reach the browser |
| Local LLM | Ollama (llama3 / mistral / gemma3 / phi4 …) | Generates grounded RGA answers from Coveo search context |
| Cloud LLM | Coveo CRGA (Professor Oak) | SSE stream consumed server-side, returned as JSON with citations |
| Backend | Flask 2.x | Proxies Coveo REST, streams CRGA, drives the agent loop, injects credentials |
| Pokémon data | PokéAPI + Serebii Pokéarth | Stats, moves, types, encounter locations, region map images |
| Artwork | pokemondb.net CDN | High-res artwork for the photo card; sprite thumbnails for the sidebar and similar-Pokémon grid |

---

## Features

- **3-Column Dark Dashboard** — sticky left sidebar (type chips + generation filter + habitat map card), scrollable center column (search, photo card, results, similar Pokémon), sticky right panel (base stats, moves table, type effectiveness, AI recommendation).
- **Natural Language Search** — powered by Coveo's semantic index with a custom Semantic-PokEncoder KNN ranking function.
- **Dual Generative Answer Modes** — switch between Professor Oak (Coveo CRGA) for cloud answers and any local Ollama model for fully offline inference. Model selector always visible in the top bar.
- **Type & Generation Filters** — sidebar chips drive Coveo facets; selecting a result highlights the Pokémon's types and dims all others.
- **Habitat Map Card** — encounter locations grouped by generation and region, with a live Serebii Pokéarth region image and PokéMaps deep-links.
- **Similar Pokémon Grid** — Coveo "More Like This" returns semantically similar Pokémon as 3-column sprite cards.
- **Stats · Moves · Type Effectiveness** — animated stat bars, scrollable level-up moves table, and a Weak To / Strong Against matchup grid.

---

## Quick Start

**1. Clone & create virtualenv**
```bash
git clone <repo> && cd pokedex
python -m venv .venv && source .venv/bin/activate
```

**2. Install dependencies**
```bash
pip install flask flask-cors python-dotenv requests ollama
```

**3. Configure environment**
```bash
cp .env.example .env
# Fill in your Coveo credentials
```

**4. Pull an Ollama model**
```bash
ollama pull llama3
```

**5. Run**
```bash
python app.py
# Open http://127.0.0.1:5003/dashboard
```

---

## Environment Variables

Copy `.env.example` to `.env` and set:

| Variable | Default | Description |
|---|---|---|
| `COVEO_ACCESS_TOKEN` | — | Coveo API key (search + CRGA) |
| `COVEO_ORGANIZATION_ID` | — | Coveo org ID |
| `COVEO_PIPELINE` | `default` | Query pipeline name |
| `COVEO_RGA_PIPELINE` | `default` | RGA-enabled pipeline |
| `COVEO_SEARCH_HUB` | `PokedexUI` | Search hub name |
| `OLLAMA_MODEL` | `llama3` | Default local model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama host |

---

## API Routes

| Method | Route | Description |
|---|---|---|
| GET | `/` | Original Pokédex device UI (`index.html`) |
| GET | `/dashboard` | Dark 3-column dashboard (`dashboard.html`) — main entry point |
| GET | `/api/coveo-token` | Returns `{token, organizationId}` — API key injected server-side |
| POST | `/api/coveo-proxy` | Proxies Coveo REST calls. Body: `{method, path, body}` |
| POST | `/api/rga` | Ollama RGA. Body: `{query, context[]}`. Returns `{answer}` |
| POST | `/api/rga-coveo` | Coveo CRGA (Professor Oak). Returns `{answer, citations}` |
| POST | `/api/ask` | Full agentic loop. Body: `{query}`. Returns `{message, pokemon_list}` |
| POST | `/api/set-model` | Hot-swaps the active Ollama model. Body: `{model}` |
| GET | `/api/models` | Lists all locally pulled Ollama models |
| GET | `/images/<filename>` | Serves artwork from local `pokemon_images/` |

---

## File Map

| File | Responsibility |
|---|---|
| `app.py` | Flask server — all routes, Coveo proxy, CRGA stream handler, Ollama RGA, model selector |
| `agent.py` | Agentic loop — `_coveo_search()`, `generate_rga_answer()`, `run_agent()` |
| `frontend/dashboard.html` | 3-column dashboard shell; Jinja2 template for org ID injection |
| `frontend/dashboard.css` | Dark dashboard design system |
| `frontend/dashboard.js` | Main controller — Coveo engine init, search, PokéAPI, map card, similar Pokémon |
| `frontend/type-colors.js` | Exported `TYPE_COLORS` map — canonical type → `{bg, text}` colour pairs |
| `frontend/index.html` | Original Pokédex-device-shaped UI (red chrome) |
| `frontend/pokedex-atomic.js` | Atomic engine init and Flask proxy bridge for the device UI |
| `frontend/pokedex-styles.css` | CSS device chrome for the original device UI |
| `frontend/result-template.js` | Coveo Atomic result template for Pokémon cards |
| `.env.example` | Template for all required environment variables |
| `eval_cases.json` | Ground-truth query → expected Pokémon pairs for search quality evaluation |
| `eval_llm_comparison.py` | Head-to-head eval: Coveo CRGA vs Ollama answer quality |
| `tune_cosine_threshold.py` | Threshold tuner for the Semantic-PokEncoder KNN ranking function |
| `test_e2e_pokedex.py` | End-to-end integration tests against a live Coveo org |

---

## Supported Models

The model selector in the dashboard top bar exposes:

- **Professor-Oak (Coveo)** — cloud CRGA with inline citations
- **llama3** · **llama3.1** · **mistral** · **gemma3** · **phi4** — local Ollama inference

Any additional model pulled via `ollama pull <model>` will appear automatically.

---

## Security

Coveo API keys are never exposed to the browser. The `/api/coveo-proxy` and `/api/rga-coveo` routes inject the `COVEO_ACCESS_TOKEN` header server-side for every request. The `/api/coveo-token` endpoint returns only what Coveo Atomic needs to initialise its headless engine.
