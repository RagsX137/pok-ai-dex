# Coveo Atomic Pokédex Frontend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Pokédex-device-shaped single-page frontend using Coveo Atomic web components (headless engine) that connects to the existing Flask/Ollama backend, shows Pokémon results as cards, and exposes Coveo features: Query Suggest, Facets, RGA (Relevance Generative Answering), and a model-selector dropdown.

**Architecture:** The frontend is a pure static HTML+CSS+JS file (`frontend/index.html`) served by Flask. It uses Coveo Atomic web components loaded from the Coveo CDN — no build step. A thin JS bridge intercepts Atomic's query events and proxies them through a local Flask endpoint (`/api/coveo-proxy`) that talks to the Coveo platform, so no API keys are exposed to the browser. A second endpoint (`/api/ask`) handles the Ollama RGA path. The Pokédex device chrome (red casing, screen, control buttons, bottom panels) is pure CSS — Atomic components are mounted inside it.

**Tech Stack:** Coveo Atomic (CDN, `@coveo/atomic` web components), Coveo Headless (bundled with Atomic), Vanilla JS (ES modules), CSS custom properties, Flask 3.x, Ollama Python SDK (`ollama`), existing `pokemon_db.csv` + `pokemon_images/`

## Global Constraints

- No npm/node build step — everything is CDN or inline. Flask serves the single HTML file.
- Coveo Atomic version: `3.x` (latest stable) loaded from `https://static.cloud.coveo.com/atomic/v3/atomic.esm.js`
- Ollama model: configurable via UI dropdown; default `llama3` (or whatever is pulled locally)
- The Pokédex device shape is defined by CSS only — no external image assets for the chrome
- All Pokémon type colors follow the canonical Pokémon game palette (see Task 1)
- `pokemon_db.csv` and `pokemon_images/` must already exist (run the scrapers once first)
- Flask runs on `http://localhost:5000`
- All Coveo credentials (`ACCESS_TOKEN`, `ORGANIZATION_ID`, `PIPELINE`) are set as env vars or in a `.env` file — never hardcoded in JS

---

## File Map

| File | Responsibility |
|---|---|
| `frontend/index.html` | Single-page Pokédex UI — Atomic components mounted inside CSS device chrome |
| `frontend/pokedex-styles.css` | Device chrome CSS (red casing, screen bezel, control row, bottom panels) |
| `frontend/pokedex-atomic.js` | Atomic engine init, bridge between Atomic events and Flask proxy, RGA/Ollama integration, model-selector wiring |
| `frontend/type-colors.js` | Canonical Pokémon type → CSS color map (exported const) |
| `frontend/result-template.js` | Coveo Atomic result template (custom `<atomic-result-template>` content) |
| `app.py` | Flask server — add `/api/coveo-proxy` and `/api/rga` endpoints alongside existing `/api/ask` |
| `agent.py` | Add `generate_rga_answer(query, context_snippets)` that calls Ollama with retrieved context |
| `.env.example` | Template for required env vars |

---

## Task 1: Device Chrome CSS — the Pokédex shell

**Files:**
- Create: `frontend/pokedex-styles.css`
- Create: `frontend/type-colors.js`

**Interfaces:**
- Produces: CSS custom properties `--screen-bg`, `--device-red`, `--screen-text`; CSS classes `.pokedex-device`, `.pokedex-screen`, `.pokedex-bottom-photo`, `.pokedex-bottom-evolutions`, `.pokedex-controls`, `.type-badge`
- Produces: `TYPE_COLORS` exported const from `type-colors.js`

- [ ] **Step 1: Create `frontend/type-colors.js`**

```js
// Canonical Pokémon type color palette
export const TYPE_COLORS = {
  fire:     { bg: '#FF9C54', text: '#7C1F00' },
  water:    { bg: '#4FC1FF', text: '#003A7C' },
  grass:    { bg: '#63BB5B', text: '#1A4A00' },
  electric: { bg: '#F3D23B', text: '#5A3E00' },
  psychic:  { bg: '#FF6B81', text: '#5A0020' },
  ice:      { bg: '#74CEC0', text: '#003A38' },
  dragon:   { bg: '#6F35FC', text: '#EDE9FF' },
  dark:     { bg: '#5A5365', text: '#EDE9FF' },
  fairy:    { bg: '#EC8FE6', text: '#5A005A' },
  fighting: { bg: '#CE4069', text: '#fff' },
  poison:   { bg: '#AB6AC8', text: '#fff' },
  ground:   { bg: '#D97845', text: '#fff' },
  rock:     { bg: '#C9B78B', text: '#3A2800' },
  bug:      { bg: '#90C12C', text: '#213800' },
  ghost:    { bg: '#5269AC', text: '#fff' },
  steel:    { bg: '#5A8EA1', text: '#fff' },
  normal:   { bg: '#9099A1', text: '#fff' },
  flying:   { bg: '#89AAE3', text: '#001A5A' },
};
```

- [ ] **Step 2: Create `frontend/pokedex-styles.css`**

```css
/* ====================================================
   Pokédex Device Chrome — matches the hand-drawn sketch
   ==================================================== */
:root {
  --device-red: #d32f2f;
  --device-dark-red: #9a0007;
  --screen-bg: #1a1f3a;
  --screen-text: #f0d040;
  --screen-border: #c8c8c8;
  --bottom-white: #f9f9f9;
  --bottom-cyan: #4dd0e1;
  --control-row-bg: #e8e8e8;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #1a1a2e;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 100vh;
  padding: 24px 16px;
  font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
}

/* ── Outer device body ── */
.pokedex-device {
  background: var(--device-red);
  border-radius: 20px 20px 12px 12px;
  width: 380px;
  max-width: 100%;
  box-shadow: 4px 6px 0 var(--device-dark-red), 0 12px 32px rgba(0,0,0,0.6);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Top bar: camera lens + LEDs + model selector ── */
.pokedex-top-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px 10px;
  background: var(--device-red);
}
.pokedex-lens {
  width: 56px; height: 56px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #81d4fa, #0288d1);
  border: 4px solid #fff;
  flex-shrink: 0;
}
.pokedex-leds {
  display: flex; gap: 8px; margin-left: 4px;
}
.led {
  width: 14px; height: 14px;
  border-radius: 50%;
}
.led-red    { background: #ff4444; box-shadow: 0 0 6px #ff4444; }
.led-yellow { background: #ffcc00; box-shadow: 0 0 6px #ffcc00; }
.led-green  { background: #44dd44; box-shadow: 0 0 6px #44dd44; }

.pokedex-model-selector {
  margin-left: auto;
  display: flex; align-items: center; gap: 6px;
  background: #f9e400;
  border: 2px solid #333;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 13px; font-weight: 700;
  color: #1a1a1a;
  cursor: pointer;
}
.model-selector-arrow { font-size: 10px; }
#model-select {
  background: transparent; border: none; outline: none;
  font-weight: 700; font-size: 13px; cursor: pointer;
  color: #1a1a1a;
}

/* ── Screen bezel ── */
.pokedex-screen-bezel {
  background: #d8d8d8;
  margin: 0 12px 8px;
  border-radius: 10px;
  padding: 10px;
  box-shadow: inset 0 2px 4px rgba(0,0,0,0.3);
}
.screen-indicator-dots {
  display: flex; justify-content: center; gap: 8px; margin-bottom: 6px;
}
.screen-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #cc2222;
}

/* ── Screen area (Atomic results mount here) ── */
.pokedex-screen {
  background: var(--screen-bg);
  border-radius: 6px;
  min-height: 320px;
  padding: 12px;
  color: var(--screen-text);
  font-family: "Courier New", monospace;
  overflow-y: auto;
  position: relative;
}

/* Search bar inside screen */
.screen-search-row {
  display: flex; gap: 6px; margin-bottom: 10px;
}
atomic-search-box {
  flex: 1;
  --atomic-primary-color: #f0d040;
  --atomic-neutral-dark-900: #f0d040;
  --atomic-background-color: #0f1228;
  --atomic-font-family: "Courier New", monospace;
}

/* RGA answer panel */
.rga-panel {
  background: rgba(240,208,64,0.08);
  border: 1px solid rgba(240,208,64,0.25);
  border-radius: 5px;
  padding: 8px 10px;
  font-size: 12px;
  color: var(--screen-text);
  margin-bottom: 10px;
  min-height: 40px;
  line-height: 1.5;
}
.rga-label {
  font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase;
  color: rgba(240,208,64,0.5); margin-bottom: 4px;
}

/* Stats row inside screen */
.screen-stats-row {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 4px; margin-top: 8px;
}
.stat-cell {
  text-align: center; font-size: 11px;
  color: var(--screen-text);
  padding: 3px;
  border-bottom: 1px solid rgba(240,208,64,0.3);
}
.stat-cell .stat-label { opacity: 0.55; font-size: 9px; text-transform: uppercase; }

/* Moves section */
.screen-section-label {
  font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;
  color: rgba(240,208,64,0.55); margin: 8px 0 4px;
}

/* ── Control row below screen ── */
.pokedex-controls {
  background: var(--control-row-bg);
  margin: 0 12px;
  border-radius: 6px;
  padding: 8px 12px;
  display: flex; align-items: center; gap: 10px;
}
.ctrl-power-btn {
  width: 32px; height: 32px; border-radius: 50%;
  background: #cc2222;
  border: 3px solid #880000;
  box-shadow: 0 2px 4px rgba(0,0,0,0.4);
  cursor: pointer; flex-shrink: 0;
}
.ctrl-type-badges { display: flex; gap: 4px; flex: 1; }
.type-badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px; font-weight: 700;
  cursor: pointer; text-transform: capitalize;
  transition: opacity 0.15s;
}
.type-badge:hover { opacity: 0.8; }
.type-badge.active { outline: 2px solid #fff; }
.ctrl-hamburger {
  display: flex; flex-direction: column; gap: 3px; cursor: pointer; margin-left: auto;
}
.ctrl-hamburger span {
  display: block; width: 22px; height: 2px; background: #555;
}

/* ── Bottom half: photo card + evolutions card ── */
.pokedex-bottom {
  display: grid; grid-template-columns: 1fr auto;
  gap: 8px; margin: 8px 12px 14px;
}
.pokedex-bottom-photo {
  background: var(--bottom-white);
  border-radius: 8px;
  padding: 14px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 130px;
  border: 2px solid #ddd;
}
.photo-sprite {
  width: 90px; height: 90px; object-fit: contain;
}
.photo-name {
  font-size: 18px; font-weight: 900;
  color: #2255cc; margin-top: 6px; text-align: center;
  font-family: "Comic Sans MS", "Chalkboard SE", cursive;
  line-height: 1.2;
}
.photo-placeholder {
  font-size: 12px; color: #aaa; text-align: center;
}

.pokedex-bottom-evolutions {
  background: var(--bottom-cyan);
  border-radius: 8px;
  padding: 10px 8px;
  width: 100px;
  display: flex; flex-direction: column; gap: 2px;
  border: 2px solid #0097a7;
}
.evo-title {
  font-size: 10px; font-weight: 800; color: #004D56; text-align: center;
  text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;
}
.evo-chain {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
}
.evo-box {
  background: #b2ebf2;
  border: 1.5px solid #0097a7;
  border-radius: 4px;
  width: 80px; padding: 4px 6px;
  font-size: 10px; font-weight: 700; color: #004D56;
  text-align: center;
  cursor: pointer;
}
.evo-box:hover { background: #e0f7fa; }
.evo-arrow {
  font-size: 10px; color: #00696f;
  display: flex; align-items: center; gap: 2px;
}
.evo-arrow .evo-level {
  font-size: 9px; color: #004D56; font-weight: 700;
}

/* ── Atomic overrides — dark screen theme ── */
atomic-result-list {
  --atomic-result-separator-color: rgba(240,208,64,0.2);
}

/* ── Facets panel (hamburger menu) ── */
.facets-drawer {
  display: none;
  position: fixed; top: 0; right: 0;
  width: 260px; height: 100vh;
  background: #fff;
  box-shadow: -4px 0 20px rgba(0,0,0,0.3);
  z-index: 100;
  padding: 20px 16px;
  overflow-y: auto;
}
.facets-drawer.open { display: block; }
.facets-close {
  font-size: 18px; cursor: pointer; float: right; margin-bottom: 12px;
}

/* ── Query Suggest dropdown ── */
atomic-search-box::part(suggestions-wrapper) {
  background: #0f1228;
  border: 1px solid rgba(240,208,64,0.3);
  color: #f0d040;
}
```

- [ ] **Step 3: Verify CSS visually** — open `frontend/pokedex-styles.css` in a browser via a simple test HTML wrapper to check the device shape renders correctly before wiring Atomic.

---

## Task 2: Flask backend additions — proxy + RGA endpoint

**Files:**
- Create: `app.py` (new file if not yet created — scaffold from architecture plan)
- Create: `agent.py` (add `generate_rga_answer`)
- Create: `.env.example`

**Interfaces:**
- Produces: `GET /` → serves `frontend/index.html`
- Produces: `POST /api/coveo-proxy` → accepts `{method, path, body}`, proxies to Coveo REST, returns JSON
- Produces: `POST /api/rga` → accepts `{query, context}`, calls Ollama, returns `{answer: str}`
- Produces: `GET /images/<filename>` → serves `pokemon_images/`
- Produces: `POST /api/ask` → existing agentic tool-call loop (unchanged from original plan)

- [ ] **Step 1: Create `.env.example`**

```
# Coveo credentials
COVEO_ACCESS_TOKEN=your-coveo-access-token-here
COVEO_ORGANIZATION_ID=your-org-id-here
COVEO_PIPELINE=default
COVEO_SEARCH_HUB=PokedexUI

# Ollama
OLLAMA_MODEL=llama3
OLLAMA_BASE_URL=http://localhost:11434
```

- [ ] **Step 2: Create `app.py`**

```python
import os, json
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import requests as req_lib
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

IMAGES_DIR = Path(__file__).parent / "pokemon_images"
FRONTEND_DIR = Path(__file__).parent / "frontend"
COVEO_ORG    = os.getenv("COVEO_ORGANIZATION_ID", "")
COVEO_TOKEN  = os.getenv("COVEO_ACCESS_TOKEN", "")
COVEO_BASE   = f"https://{COVEO_ORG}.org.coveo.com"

# ── Static frontend ──────────────────────────────────────────
@app.route("/")
def index():
    return (FRONTEND_DIR / "index.html").read_text()

@app.route("/frontend/<path:filename>")
def frontend_static(filename):
    return send_from_directory(FRONTEND_DIR, filename)

@app.route("/images/<filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)

# ── Coveo proxy ──────────────────────────────────────────────
@app.route("/api/coveo-proxy", methods=["POST"])
def coveo_proxy():
    """
    Body: { "method": "POST", "path": "/rest/search/v2", "body": {...} }
    Proxies the request to Coveo REST API and returns the raw JSON response.
    Injects COVEO_ACCESS_TOKEN server-side so the browser never sees the token.
    """
    data   = request.get_json(force=True)
    method = data.get("method", "POST").upper()
    path   = data.get("path", "/rest/search/v2")
    body   = data.get("body", {})

    url  = f"{COVEO_BASE}{path}?organizationId={COVEO_ORG}"
    hdrs = {
        "Authorization": f"Bearer {COVEO_TOKEN}",
        "Content-Type":  "application/json",
    }

    resp = req_lib.request(method, url, json=body, headers=hdrs, timeout=15)
    return jsonify(resp.json()), resp.status_code

# ── Ollama RGA ───────────────────────────────────────────────
@app.route("/api/rga", methods=["POST"])
def rga():
    """
    Body: { "query": str, "context": [{"title": str, "excerpt": str}] }
    Returns: { "answer": str }
    """
    from agent import generate_rga_answer
    data    = request.get_json(force=True)
    query   = data.get("query", "")
    context = data.get("context", [])
    answer  = generate_rga_answer(query, context)
    return jsonify({"answer": answer})

# ── Original agentic ask ─────────────────────────────────────
@app.route("/api/ask", methods=["POST"])
def ask():
    from agent import run_agent
    data  = request.get_json(force=True)
    query = data.get("query", "")
    result = run_agent(query)
    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
```

- [ ] **Step 3: Add `generate_rga_answer` to `agent.py`**

```python
import os
import ollama

OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

_client = ollama.Client(host=OLLAMA_BASE_URL)

def generate_rga_answer(query: str, context: list[dict]) -> str:
    """
    Given a user query and a list of Coveo result snippets,
    ask Ollama to generate a grounded answer (RGA / RAG style).

    context items: [{"title": str, "excerpt": str}, ...]
    Returns: answer string
    """
    snippets = "\n\n".join(
        f"[{i+1}] {c.get('title','')}\n{c.get('excerpt','')}"
        for i, c in enumerate(context[:5])
    )
    prompt = (
        f"You are the Pokédex AI. A trainer asked: \"{query}\"\n\n"
        f"Here are relevant Pokédex entries:\n{snippets}\n\n"
        f"Answer the trainer's question concisely using only the information above. "
        f"Do not make up stats. If you don't know, say so."
    )
    resp = _client.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp["message"]["content"]


def run_agent(query: str) -> dict:
    """
    Agentic tool-calling loop (defined in original architecture plan).
    Placeholder — implement with pokedex_tools.py.
    """
    from pokedex_tools import look_up_by_type, look_up_by_generation, get_pokemon_detail

    tools = [
        {
            "type": "function",
            "function": {
                "name": "look_up_by_type",
                "description": "Find Pokémon by elemental type",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "description": "Pokémon type e.g. fire, water"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "look_up_by_generation",
                "description": "Find Pokémon by game generation (1–9)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "generation": {"type": "integer"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["generation"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_pokemon_detail",
                "description": "Get full details for a single named Pokémon",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
    ]

    messages = [{"role": "user", "content": query}]
    resp = _client.chat(model=OLLAMA_MODEL, messages=messages, tools=tools)

    pokemon_list = []
    message = resp["message"]

    if message.get("tool_calls"):
        for call in message["tool_calls"]:
            fn   = call["function"]["name"]
            args = call["function"]["arguments"]
            if fn == "look_up_by_type":
                pokemon_list = look_up_by_type(**args)
            elif fn == "look_up_by_generation":
                pokemon_list = look_up_by_generation(**args)
            elif fn == "get_pokemon_detail":
                result = get_pokemon_detail(**args)
                pokemon_list = [result] if result else []

        messages.append(message)
        messages.append({
            "role": "tool",
            "content": json.dumps(pokemon_list),
        })
        final = _client.chat(model=OLLAMA_MODEL, messages=messages)
        prose = final["message"]["content"]
    else:
        prose = message.get("content", "")

    return {"message": prose, "pokemon_list": pokemon_list}
```

- [ ] **Step 4: Create `pokedex_tools.py`**

```python
import json
import pandas as pd
from pathlib import Path

_CSV = Path(__file__).parent / "pokemon_db.csv"
_GEN_MAP = {
    1: (1, 151), 2: (152, 251), 3: (252, 386), 4: (387, 493),
    5: (494, 649), 6: (650, 721), 7: (722, 809), 8: (810, 905), 9: (906, 1025),
}

def _load_df():
    df = pd.read_csv(_CSV)
    df["pokedex_num"] = df["pokedex_num"].astype(str).str.zfill(4)
    return df

def _row_to_dict(row: pd.Series) -> dict:
    name = row["pokemon"].lower()
    return {
        "name":        row["pokemon"],
        "number":      row["pokedex_num"],
        "type1":       row["elem_1"],
        "type2":       row["elem_2"] if pd.notna(row["elem_2"]) else None,
        "species":     row["species"],
        "hp":          int(row["hp"]),
        "attack":      int(row["attack"]),
        "defense":     int(row["defense"]),
        "sp_atk":      int(row["sp_atk"]),
        "sp_def":      int(row["sp_def"]),
        "speed":       int(row["speed"]),
        "total":       int(row["total"]),
        "image_url":   f"/images/{name}_image.jpg",
    }

def look_up_by_type(type: str, limit: int = 20) -> list[dict]:
    df  = _load_df()
    t   = type.strip().capitalize()
    mask = (df["elem_1"].str.upper() == t.upper()) | (df["elem_2"].str.upper() == t.upper())
    return [_row_to_dict(r) for _, r in df[mask].head(limit).iterrows()]

def look_up_by_generation(generation: int, limit: int = 20) -> list[dict]:
    lo, hi = _GEN_MAP.get(generation, (1, 151))
    df = _load_df()
    df["num_int"] = df["pokedex_num"].astype(int)
    mask = (df["num_int"] >= lo) & (df["num_int"] <= hi)
    return [_row_to_dict(r) for _, r in df[mask].head(limit).iterrows()]

def get_pokemon_detail(name: str) -> dict | None:
    df   = _load_df()
    mask = df["pokemon"].str.lower() == name.strip().lower()
    rows = df[mask]
    if rows.empty:
        return None
    return _row_to_dict(rows.iloc[0])
```

- [ ] **Step 5: Install dependencies**

```bash
pip install flask flask-cors python-dotenv ollama requests
```

Expected output: `Successfully installed ...` (no errors)

- [ ] **Step 6: Smoke-test the Flask server**

```bash
python app.py &
curl -s http://localhost:5000/ | head -5
# expected: <!DOCTYPE html> or first lines of index.html (will be empty until Task 3)
curl -s -X POST http://localhost:5000/api/rga \
  -H "Content-Type: application/json" \
  -d '{"query":"What type is Pikachu?","context":[{"title":"Pikachu","excerpt":"Pikachu is an Electric-type Pokémon."}]}'
# expected: {"answer":"Pikachu is an Electric-type Pokémon..."}
```

- [ ] **Step 7: Commit**

```bash
git add app.py agent.py pokedex_tools.py .env.example
git commit -m "feat: add Flask server with Coveo proxy, Ollama RGA, and agentic ask endpoints"
```

---

## Task 3: Coveo Atomic integration JS

**Files:**
- Create: `frontend/pokedex-atomic.js`

**Interfaces:**
- Consumes: `COVEO_ORGANIZATION_ID`, `COVEO_ACCESS_TOKEN` via `/api/coveo-proxy` (never in JS)
- Consumes: `/api/rga` endpoint from Task 2
- Consumes: `TYPE_COLORS` from `frontend/type-colors.js`
- Produces: Initializes `@coveo/atomic` headless engine, wires query suggest, facets, RGA

- [ ] **Step 1: Create `frontend/pokedex-atomic.js`**

```js
import { TYPE_COLORS } from './type-colors.js';

// ────────────────────────────────────────────────────────────
// 1.  Bootstrap Coveo Atomic through the Flask proxy
//     (no Coveo token in the browser — all auth is server-side)
// ────────────────────────────────────────────────────────────
async function getSearchToken() {
  // The proxy endpoint signs requests with COVEO_ACCESS_TOKEN server-side.
  // For headless init we need a search token; request one from the proxy.
  const resp = await fetch('/api/coveo-proxy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      method: 'POST',
      path: '/rest/search/v2/token',
      body: { userIds: [{ name: 'pokedex-user', type: 'User' }] },
    }),
  });
  const data = await resp.json();
  return data.token;   // Coveo search token scoped to this user
}

// ────────────────────────────────────────────────────────────
// 2.  Initialize the atomic-search-interface element
// ────────────────────────────────────────────────────────────
async function initAtomic() {
  const searchInterface = document.querySelector('atomic-search-interface');
  if (!searchInterface) return;

  const token = await getSearchToken();
  const orgId = document.body.dataset.coveoOrg;  // set via data attr in HTML

  await searchInterface.initialize({
    accessToken: token,
    organizationId: orgId,
    search: {
      pipeline:   'PokedexPipeline',
      searchHub: 'PokedexUI',
    },
  });

  // Trigger an initial search to populate results on load
  searchInterface.executeFirstSearch();
}

// ────────────────────────────────────────────────────────────
// 3.  Coveo result → Pokédex detail panel wiring
//     When user clicks a result, populate the bottom panel
// ────────────────────────────────────────────────────────────
function wireResultClicks() {
  document.addEventListener('atomic/result/select', (e) => {
    const result = e.detail?.result;
    if (!result) return;

    const name     = result.title ?? result.raw?.pokemon ?? '';
    const imageUrl = result.raw?.image_url ?? `/images/${name.toLowerCase()}_image.jpg`;
    const type1    = result.raw?.type1 ?? '';
    const type2    = result.raw?.type2 ?? '';
    const evo      = result.raw?.evolutions ?? [];

    // Photo panel
    document.querySelector('.photo-sprite').src = imageUrl;
    document.querySelector('.photo-name').textContent = name;

    // Type badges in control row
    renderTypeBadges([type1, type2].filter(Boolean));

    // Stats row in screen
    renderStatsRow({
      hp:      result.raw?.hp,
      attack:  result.raw?.attack,
      defense: result.raw?.defense,
      speed:   result.raw?.speed,
    });

    // Evolutions panel
    renderEvolutionChain(evo);
  });
}

// ────────────────────────────────────────────────────────────
// 4.  RGA — called after Coveo returns results
//     Sends top-5 snippets to /api/rga and streams answer
// ────────────────────────────────────────────────────────────
async function fetchRGAAnswer(query, results) {
  const context = results.slice(0, 5).map(r => ({
    title:   r.title ?? '',
    excerpt: r.raw?.excerpt ?? r.excerpt ?? '',
  }));

  const rgaPanel = document.querySelector('.rga-panel');
  rgaPanel.textContent = '…';

  const resp = await fetch('/api/rga', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, context }),
  });
  const data = await resp.json();
  rgaPanel.textContent = data.answer ?? '—';
}

// Wire to Atomic's search success event
function wireRGA() {
  document.addEventListener('atomic/search/success', (e) => {
    const query   = document.querySelector('atomic-search-box')?.shadowRoot
                        ?.querySelector('input')?.value ?? '';
    const results = e.detail?.results ?? [];
    if (query && results.length) fetchRGAAnswer(query, results);
  });
}

// ────────────────────────────────────────────────────────────
// 5.  Type badge quick-filter buttons
// ────────────────────────────────────────────────────────────
function renderTypeBadges(types) {
  const container = document.querySelector('.ctrl-type-badges');
  container.innerHTML = '';
  types.forEach(t => {
    const colors = TYPE_COLORS[t.toLowerCase()] ?? { bg: '#888', text: '#fff' };
    const btn = document.createElement('button');
    btn.className = 'type-badge';
    btn.textContent = t;
    btn.style.background = colors.bg;
    btn.style.color = colors.text;
    btn.addEventListener('click', () => filterByType(t));
    container.appendChild(btn);
  });
}

function filterByType(type) {
  // Use Coveo's facet value selection via custom event
  const facetEl = document.querySelector(`atomic-facet[field="type1"]`);
  if (facetEl) {
    const event = new CustomEvent('atomic/facet/select', {
      bubbles: true,
      detail: { facetId: 'type1', facetValue: type },
    });
    facetEl.dispatchEvent(event);
  }
}

// ────────────────────────────────────────────────────────────
// 6.  Stats row renderer
// ────────────────────────────────────────────────────────────
function renderStatsRow(stats) {
  const row = document.querySelector('.screen-stats-row');
  if (!row) return;
  const labels = { hp: 'HP', attack: 'Atk', defense: 'Def', speed: 'Spd' };
  row.innerHTML = Object.entries(labels).map(([key, label]) => `
    <div class="stat-cell">
      <div class="stat-label">${label}</div>
      <div>${stats[key] ?? '—'}</div>
    </div>
  `).join('');
}

// ────────────────────────────────────────────────────────────
// 7.  Evolution chain renderer
// ────────────────────────────────────────────────────────────
function renderEvolutionChain(chain) {
  // chain: [{name, level}, ...] — sourced from Coveo result raw field
  const container = document.querySelector('.evo-chain');
  if (!container) return;
  container.innerHTML = '';
  chain.forEach((stage, i) => {
    const box = document.createElement('div');
    box.className = 'evo-box';
    box.textContent = stage.name;
    box.addEventListener('click', () => searchPokemon(stage.name));
    container.appendChild(box);
    if (i < chain.length - 1) {
      const arrow = document.createElement('div');
      arrow.className = 'evo-arrow';
      arrow.innerHTML = `▼ <span class="evo-level">Lv.${chain[i+1].level ?? '?'}</span>`;
      container.appendChild(arrow);
    }
  });
}

function searchPokemon(name) {
  const searchBox = document.querySelector('atomic-search-box');
  if (searchBox) searchBox.setAttribute('value', name);
  document.querySelector('atomic-search-interface')?.executeFirstSearch();
}

// ────────────────────────────────────────────────────────────
// 8.  Facets drawer (hamburger menu toggle)
// ────────────────────────────────────────────────────────────
function wireFacetsDrawer() {
  const hamburger = document.querySelector('.ctrl-hamburger');
  const drawer    = document.querySelector('.facets-drawer');
  const close     = document.querySelector('.facets-close');
  hamburger?.addEventListener('click', () => drawer?.classList.toggle('open'));
  close?.addEventListener('click',     () => drawer?.classList.remove('open'));
}

// ────────────────────────────────────────────────────────────
// 9.  Model selector — updates OLLAMA_MODEL via Flask
// ────────────────────────────────────────────────────────────
function wireModelSelector() {
  document.getElementById('model-select')?.addEventListener('change', async (e) => {
    await fetch('/api/set-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: e.target.value }),
    });
  });
}

// ────────────────────────────────────────────────────────────
// 10. Boot
// ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await initAtomic();
  wireResultClicks();
  wireRGA();
  wireFacetsDrawer();
  wireModelSelector();
  renderTypeBadges(['Grass', 'Water']);  // default type badge display
});
```

- [ ] **Step 2: Add `/api/set-model` to `app.py`**

```python
# Add to app.py after the /api/rga route

_active_model = os.getenv("OLLAMA_MODEL", "llama3")

@app.route("/api/set-model", methods=["POST"])
def set_model():
    global _active_model
    data = request.get_json(force=True)
    _active_model = data.get("model", _active_model)
    os.environ["OLLAMA_MODEL"] = _active_model
    return jsonify({"model": _active_model})

@app.route("/api/models")
def list_models():
    """Return available local Ollama models."""
    import ollama as ol
    client = ol.Client(host=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    models = client.list()
    names = [m["name"] for m in models.get("models", [])]
    return jsonify({"models": names})
```

- [ ] **Step 3: Commit**

```bash
git add frontend/pokedex-atomic.js app.py
git commit -m "feat: add Coveo Atomic JS bridge, RGA wiring, model selector, type filter, evolutions panel"
```

---

## Task 4: Main HTML — assemble the Pokédex shell with Atomic components

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/result-template.js`

**Interfaces:**
- Consumes: `pokedex-styles.css`, `pokedex-atomic.js` (Task 1 + 3)
- Consumes: Flask `/` route (Task 2)
- Produces: Complete working single-page Pokédex UI with Coveo Atomic components

- [ ] **Step 1: Create `frontend/result-template.js`**

```js
// Custom Atomic result template for Pokémon cards shown inside the screen
// Registered as a web component used by <atomic-result-template>

import { TYPE_COLORS } from './type-colors.js';

export function buildResultTemplateHTML(result) {
  const name   = result.title ?? result.raw?.pokemon ?? 'Unknown';
  const num    = result.raw?.pokedex_num ?? '????';
  const type1  = result.raw?.type1 ?? '';
  const type2  = result.raw?.type2 ?? '';
  const total  = result.raw?.total ?? '—';
  const imgSrc = result.raw?.image_url ?? `/images/${name.toLowerCase()}_image.jpg`;
  const c1     = TYPE_COLORS[type1.toLowerCase()] ?? { bg: '#888', text: '#fff' };
  const c2     = type2 ? (TYPE_COLORS[type2.toLowerCase()] ?? { bg: '#888', text: '#fff' }) : null;

  return `
    <div style="display:flex;align-items:center;gap:8px;padding:6px 0;
                border-bottom:1px solid rgba(240,208,64,0.2);cursor:pointer;">
      <img src="${imgSrc}" width="40" height="40" style="object-fit:contain;flex-shrink:0;"
           onerror="this.src='/images/placeholder.png'"/>
      <div style="flex:1;min-width:0;">
        <div style="font-size:12px;font-weight:700;color:#f0d040;white-space:nowrap;
                    overflow:hidden;text-overflow:ellipsis;">${name}</div>
        <div style="font-size:10px;color:rgba(240,208,64,0.55);">#${num} · Total ${total}</div>
      </div>
      <div style="display:flex;gap:3px;flex-shrink:0;">
        <span style="background:${c1.bg};color:${c1.text};font-size:9px;font-weight:700;
                     padding:2px 5px;border-radius:3px;">${type1}</span>
        ${c2 ? `<span style="background:${c2.bg};color:${c2.text};font-size:9px;font-weight:700;
                              padding:2px 5px;border-radius:3px;">${type2}</span>` : ''}
      </div>
    </div>
  `;
}
```

- [ ] **Step 2: Create `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Pokédex — Agentic Edition</title>
  <link rel="stylesheet" href="/frontend/pokedex-styles.css" />

  <!-- Coveo Atomic from CDN — no build step -->
  <script type="module"
    src="https://static.cloud.coveo.com/atomic/v3/atomic.esm.js">
  </script>
  <link rel="stylesheet"
    href="https://static.cloud.coveo.com/atomic/v3/themes/coveo.css" />
</head>

<!--
  data-coveo-org is read by pokedex-atomic.js to initialize the engine.
  Flask injects the real value via template rendering.
-->
<body data-coveo-org="{{ COVEO_ORGANIZATION_ID }}">

<!-- ═══════════════════════════════════════════════════════════
     Facets side-drawer (opened by hamburger button)
═══════════════════════════════════════════════════════════════ -->
<div class="facets-drawer" id="facets-drawer">
  <span class="facets-close" id="facets-close">✕ Close</span>
  <h3 style="font-size:14px;margin-bottom:12px;">Filter Pokémon</h3>

  <!-- These facets reference Coveo fields — must match your index field names -->
  <atomic-facet field="type1" label="Primary Type"
    display-values-as="link" number-of-values="18">
  </atomic-facet>

  <atomic-facet field="type2" label="Secondary Type"
    display-values-as="link" number-of-values="18"
    style="margin-top:16px;">
  </atomic-facet>

  <atomic-numeric-facet field="total" label="Base Stat Total"
    style="margin-top:16px;">
    <atomic-numeric-range start="0"   end="300" label="0–300"></atomic-numeric-range>
    <atomic-numeric-range start="300" end="450" label="300–450"></atomic-numeric-range>
    <atomic-numeric-range start="450" end="600" label="450–600"></atomic-numeric-range>
    <atomic-numeric-range start="600" end="999" label="600+"></atomic-numeric-range>
  </atomic-numeric-facet>

  <atomic-facet field="generation" label="Generation"
    style="margin-top:16px;">
  </atomic-facet>
</div>

<!-- ═══════════════════════════════════════════════════════════
     Main Pokédex device
═══════════════════════════════════════════════════════════════ -->
<atomic-search-interface id="atomic-search-interface">
<div class="pokedex-device">

  <!-- ── TOP BAR: lens + LEDs + model selector ── -->
  <div class="pokedex-top-bar">
    <div class="pokedex-lens"></div>
    <div class="pokedex-leds">
      <div class="led led-red"></div>
      <div class="led led-yellow"></div>
      <div class="led led-green"></div>
    </div>
    <div class="pokedex-model-selector">
      <span class="model-selector-arrow">▼</span>
      <select id="model-select" title="Select Ollama model">
        <option value="llama3">llama3</option>
        <option value="llama3.1">llama3.1</option>
        <option value="mistral">mistral</option>
        <option value="gemma3">gemma3</option>
        <option value="phi4">phi4</option>
      </select>
    </div>
  </div>

  <!-- ── SCREEN BEZEL ── -->
  <div class="pokedex-screen-bezel">
    <div class="screen-indicator-dots">
      <div class="screen-dot"></div>
      <div class="screen-dot"></div>
    </div>

    <!-- ── SCREEN ── -->
    <div class="pokedex-screen">

      <!-- Search bar -->
      <div class="screen-search-row">
        <atomic-search-box
          number-of-queries="5"
          minimum-query-length="1"
          clear-filters="false">
        </atomic-search-box>
      </div>

      <!-- RGA / Ollama answer panel -->
      <div class="rga-label">Pokédex AI</div>
      <div class="rga-panel" id="rga-panel">
        Ask me anything about Pokémon…
      </div>

      <!-- Quick stat row (populated on result select) -->
      <div class="screen-section-label">Stats</div>
      <div class="screen-stats-row" id="screen-stats-row">
        <div class="stat-cell"><div class="stat-label">HP</div><div>—</div></div>
        <div class="stat-cell"><div class="stat-label">Atk</div><div>—</div></div>
        <div class="stat-cell"><div class="stat-label">Def</div><div>—</div></div>
        <div class="stat-cell"><div class="stat-label">Spd</div><div>—</div></div>
      </div>

      <!-- Moves section placeholder -->
      <div class="screen-section-label">Moves</div>
      <div id="moves-list" style="font-size:11px;color:rgba(240,208,64,0.7);min-height:28px;">
        —
      </div>

      <!-- Coveo Atomic result list (scrollable, inside screen) -->
      <div class="screen-section-label" style="margin-top:10px;">Results</div>
      <atomic-result-list
        display="list"
        image-size="none"
        density="compact">
        <atomic-result-template>
          <template>
            <!-- Inline template — Atomic renders one per result -->
            <atomic-result-section-title>
              <atomic-result-link></atomic-result-link>
            </atomic-result-section-title>
            <atomic-result-section-badges>
              <atomic-field-condition must-match-field="type1">
                <atomic-result-badge field="type1" label="Type 1"></atomic-result-badge>
              </atomic-field-condition>
              <atomic-field-condition must-match-field="type2">
                <atomic-result-badge field="type2" label="Type 2"></atomic-result-badge>
              </atomic-field-condition>
            </atomic-result-section-badges>
            <atomic-result-section-excerpt>
              <atomic-result-text field="excerpt" should-highlight="true"></atomic-result-text>
            </atomic-result-section-excerpt>
          </template>
        </atomic-result-template>
      </atomic-result-list>

      <!-- Pagination -->
      <atomic-pager style="margin-top:8px;"></atomic-pager>

    </div><!-- /.pokedex-screen -->
  </div><!-- /.pokedex-screen-bezel -->

  <!-- ── CONTROLS ROW ── -->
  <div class="pokedex-controls">
    <button class="ctrl-power-btn" title="Reset search" id="power-btn"></button>
    <div class="ctrl-type-badges" id="type-badges">
      <!-- populated by JS: renderTypeBadges() -->
    </div>
    <div class="ctrl-hamburger" id="hamburger-btn" title="Filters">
      <span></span><span></span><span></span>
    </div>
  </div>

  <!-- ── BOTTOM PANELS ── -->
  <div class="pokedex-bottom">
    <!-- Photo + name card -->
    <div class="pokedex-bottom-photo">
      <img class="photo-sprite"
           src="/images/placeholder.png"
           alt="Pokémon sprite"
           onerror="this.style.display='none'" />
      <div class="photo-name" id="photo-name">Pokémon</div>
    </div>

    <!-- Evolutions card -->
    <div class="pokedex-bottom-evolutions">
      <div class="evo-title">Evolutions</div>
      <div class="evo-chain" id="evo-chain">
        <div class="evo-box" style="opacity:0.4;">—</div>
      </div>
    </div>
  </div>

</div><!-- /.pokedex-device -->
</atomic-search-interface>

<!-- Query breadcrumb (outside screen, above device — optional UX improvement) -->
<div style="margin-top:10px;width:380px;max-width:100%;">
  <atomic-breadbox></atomic-breadbox>
  <atomic-query-summary style="font-size:11px;color:#aaa;margin-top:4px;"></atomic-query-summary>
</div>

<script type="module" src="/frontend/pokedex-atomic.js"></script>
</body>
</html>
```

- [ ] **Step 3: Update Flask to inject COVEO_ORGANIZATION_ID into the HTML**

Replace the `index()` route in `app.py`:

```python
from flask import render_template_string

@app.route("/")
def index():
    html = (FRONTEND_DIR / "index.html").read_text()
    return render_template_string(html, COVEO_ORGANIZATION_ID=COVEO_ORG)
```

- [ ] **Step 4: Create a placeholder image**

```bash
# Create a minimal placeholder SVG as PNG fallback
python3 -c "
svg = '''<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"90\" height=\"90\">
  <circle cx=\"45\" cy=\"45\" r=\"44\" fill=\"#eee\" stroke=\"#ccc\" stroke-width=\"1\"/>
  <text x=\"50%\" y=\"55%\" dominant-baseline=\"middle\" text-anchor=\"middle\"
        font-size=\"28\" fill=\"#bbb\">?</text>
</svg>'''
open('pokemon_images/placeholder.png','w').write(svg)
"
```

- [ ] **Step 5: Smoke-test the full UI**

```bash
python app.py
# Open http://localhost:5000 in a browser
# Expected: Red Pokédex device with search bar on dark screen, type badges in control row,
#           LLM selector in top-right, Evolutions panel in bottom-right
```

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html frontend/result-template.js frontend/pokedex-atomic.js
git commit -m "feat: Pokédex HTML shell with Atomic search, RGA panel, control row, bottom panels"
```

---

## Task 5: Coveo index setup — push Pokémon data to Coveo

**Files:**
- Create: `coveo_push.py` — one-time script to push `pokemon_db.csv` to Coveo Push API

**Interfaces:**
- Consumes: `pokemon_db.csv`, `COVEO_ACCESS_TOKEN`, `COVEO_ORGANIZATION_ID`, `COVEO_SOURCE_ID` (new env var)
- Produces: All Pokémon records indexed in Coveo with fields: `pokemon`, `pokedex_num`, `type1`, `type2`, `species`, `hp`, `attack`, `defense`, `sp_atk`, `sp_def`, `speed`, `total`, `generation`, `image_url`

- [ ] **Step 1: Add `COVEO_SOURCE_ID` to `.env.example`**

```
# Add to .env.example:
COVEO_SOURCE_ID=your-push-source-id-here
```

- [ ] **Step 2: Create `coveo_push.py`**

```python
"""
One-time script: pushes pokemon_db.csv to a Coveo Push API source.
Run once after indexing credentials are set up in .env

Usage:
  python coveo_push.py
"""
import os, json, time, math
import pandas as pd
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ORG_ID    = os.environ["COVEO_ORGANIZATION_ID"]
TOKEN     = os.environ["COVEO_ACCESS_TOKEN"]
SOURCE_ID = os.environ["COVEO_SOURCE_ID"]
BASE      = f"https://{ORG_ID}.org.coveo.com"

GEN_MAP = {
    1: (1, 151), 2: (152, 251), 3: (252, 386), 4: (387, 493),
    5: (494, 649), 6: (650, 721), 7: (722, 809), 8: (810, 905), 9: (906, 1025),
}

def get_generation(num: int) -> int:
    for gen, (lo, hi) in GEN_MAP.items():
        if lo <= num <= hi:
            return gen
    return 0

def push_batch(documents: list[dict]):
    url  = f"{BASE}/rest/organizations/{ORG_ID}/sources/{SOURCE_ID}/documents/batch"
    hdrs = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    resp = requests.put(url, json={"addOrUpdate": documents}, headers=hdrs, timeout=30)
    resp.raise_for_status()
    return resp.json()

def build_document(row) -> dict:
    name  = row["pokemon"]
    num   = int(str(row["pokedex_num"]).lstrip("0") or "0")
    gen   = get_generation(num)
    lower = name.lower().replace(" ", "-")
    return {
        "documentId": f"pokemon://{lower}",
        "title":      name,
        "data":       (
            f"{name} is a {row['elem_1']}"
            + (f"/{row['elem_2']}" if pd.notna(row.get('elem_2')) else "")
            + f"-type Pokémon. Species: {row['species']}. "
            f"HP {row['hp']}, Attack {row['attack']}, Defense {row['defense']}, "
            f"Speed {row['speed']}. Total {row['total']}."
        ),
        "excerpt": f"#{str(num).zfill(4)} — {row['species']}",
        "uri":     row.get("url", f"https://pokemondb.net/pokedex/{lower}"),
        "metadata": {
            "pokemon":    name,
            "pokedex_num": str(num).zfill(4),
            "type1":      row["elem_1"],
            "type2":      row["elem_2"] if pd.notna(row.get("elem_2")) else "",
            "species":    row["species"],
            "hp":         int(row["hp"]),
            "attack":     int(row["attack"]),
            "defense":    int(row["defense"]),
            "sp_atk":     int(row["sp_atk"]),
            "sp_def":     int(row["sp_def"]),
            "speed":      int(row["speed"]),
            "total":      int(row["total"]),
            "generation": gen,
            "image_url":  f"/images/{lower.replace('-','')}_image.jpg",
        },
    }

def main():
    df    = pd.read_csv(Path(__file__).parent / "pokemon_db.csv")
    docs  = [build_document(r) for _, r in df.iterrows()]
    batch_size = 50
    total = len(docs)
    print(f"Pushing {total} Pokémon to Coveo in batches of {batch_size}…")
    for i in range(0, total, batch_size):
        batch = docs[i:i+batch_size]
        push_batch(batch)
        print(f"  {min(i+batch_size, total)}/{total} pushed")
        time.sleep(0.5)
    print("Done.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the push (requires Coveo Push API credentials)**

```bash
python coveo_push.py
# Expected: 50/1025 pushed … 1025/1025 pushed  Done.
```

- [ ] **Step 4: Commit**

```bash
git add coveo_push.py .env.example
git commit -m "feat: Coveo Push API script to index all Pokémon with metadata"
```

---

## Task 6: Query Suggest polish + atomic-search-box wiring

**Files:**
- Modify: `frontend/index.html` — tune `atomic-search-box` attributes
- Modify: `frontend/pokedex-atomic.js` — populate model selector from `/api/models` on load

**Interfaces:**
- Consumes: `/api/models` endpoint (Task 3)
- Produces: Model selector populated with all locally pulled Ollama models on page load

- [ ] **Step 1: Populate model selector from live Ollama models**

Add to the bottom of `initAtomic()` in `frontend/pokedex-atomic.js`:

```js
  // Populate model dropdown from live Ollama models
  try {
    const resp   = await fetch('/api/models');
    const data   = await resp.json();
    const select = document.getElementById('model-select');
    if (select && data.models?.length) {
      select.innerHTML = data.models
        .map(m => `<option value="${m}">${m}</option>`)
        .join('');
    }
  } catch (_) { /* keep static options if Ollama is offline */ }
```

- [ ] **Step 2: Wire power button to reset search**

Add to `document.addEventListener('DOMContentLoaded', ...)` in `pokedex-atomic.js`:

```js
  document.getElementById('power-btn')?.addEventListener('click', () => {
    const si = document.querySelector('atomic-search-interface');
    si?.executeFirstSearch();
    document.querySelector('.photo-name').textContent = 'Pokémon';
    document.querySelector('.photo-sprite').src = '/images/placeholder.png';
    document.querySelector('.rga-panel').textContent = 'Ask me anything about Pokémon…';
    document.querySelector('.evo-chain').innerHTML =
      '<div class="evo-box" style="opacity:0.4;">—</div>';
  });
```

- [ ] **Step 3: Final smoke test checklist**

```
✓ http://localhost:5000 renders the Pokédex device
✓ Typing in the search box triggers Atomic query suggest dropdown
✓ Submitting a search returns Coveo results in the screen panel
✓ Clicking a result populates: sprite, name, stats, type badges
✓ RGA panel fills with Ollama-generated answer after search
✓ Hamburger opens facets drawer (Type, Stat Total, Generation)
✓ Type badge quick-filter buttons filter results
✓ Model dropdown shows locally available Ollama models
✓ Power button resets the screen
✓ Evolution boxes are clickable and trigger a new search
```

- [ ] **Step 4: Final commit**

```bash
git add frontend/pokedex-atomic.js frontend/index.html
git commit -m "feat: live model selector, power-reset button, smoke-test pass"
```

---

## Self-Review — Spec Coverage

| Sketch element | Task |
|---|---|
| Red Pokédex device chrome | Task 1 CSS |
| Blue lens + LEDs | Task 1 CSS |
| Dark navy screen | Task 1 CSS |
| Yellow text / stats row (Str, Wk, Atk, Def) | Task 4 HTML + Task 3 JS |
| Moves section | Task 4 HTML (placeholder) |
| LLM model selector badge (yellow, top-right) | Task 1 CSS + Task 3 JS + Task 4 HTML |
| RGA answer (Pokédex AI text area) | Task 2 Flask `/api/rga` + Task 3 JS |
| Coveo Query Suggest | Task 4 `atomic-search-box` with `number-of-queries="5"` |
| Coveo Facets (hamburger → drawer) | Task 4 HTML + Task 3 JS |
| Type badge buttons (Grass, Water in sketch) | Task 1 CSS + Task 3 JS |
| Photo card (bottom-left) | Task 4 HTML + Task 3 JS |
| Pokémon name in photo card | Task 3 JS `wireResultClicks` |
| Evolutions card (bottom-right, with levels) | Task 4 HTML + Task 3 JS |
| Coveo RGA (push → query → answer) | Task 5 push + Task 2 + Task 3 |
| Ollama LLM integration | Task 2 `agent.py` |
| Modular file structure | File Map above |
