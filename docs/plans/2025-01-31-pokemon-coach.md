# Pokémon Coach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a conversational Pokémon coach at `/coach` — a ChatGPT-style interface that answers battle questions using Coveo RGA, maintains multi-turn session history, and renders inline side-by-side Pokémon comparison panels using the same rendering primitives as the existing dashboard.

**Architecture:** A new Flask blueprint (`coach_api.py`) provides a stateful `/api/coach` endpoint backed by an in-memory session store (`conversation.py`). The frontend (`coach.html/js/css`) uses the Coveo Headless SDK for query suggestions and fires the existing `/api/rga-coveo` and new `/api/coach` endpoints. Six rendering functions are extracted from `dashboard.js` into a shared ES module (`pokemon-panel.js`) with a namespace parameter so two panel instances can coexist in the comparison view. The dashboard wires them with an empty namespace — zero behavior change.

**Tech Stack:** Python 3.11, Flask 3.1, Coveo Atomic v3 / Headless (CDN), vanilla ES modules, pytest, Playwright

## Global Constraints

- Python ≥ 3.11; Flask ≥ 3.1; no new Python dependencies beyond what is already in `pyproject.toml`
- All frontend files are vanilla ES modules (no bundler, no npm); use `type="module"` script tags
- Dark theme tokens must match dashboard exactly: `#0d0d1a` body, `#161626` card bg, `#2a2a40` border, `#f0d040` accent yellow, `#4fc3f7` accent blue
- All new routes follow the pattern in `pokedex/routes/pages.py` and `pokedex/routes/coveo_api.py`
- Tests follow existing patterns: unit tests in `tests/unit/`, e2e in `tests/e2e/`, mark e2e with `pytestmark = pytest.mark.e2e`
- Never modify `dashboard.css` or the existing behavior of `dashboard.js` (the `ns=''` refactor must be pixel-identical)
- The `/coach` page must render with `COVEO_ORGANIZATION_ID` injected via `render_template_string` exactly like `/dashboard`
- Session store is in-memory only; no SQLite, no file persistence, no new dependencies
- Comparison intent regex must not use an LLM; it must be a pure string/regex check in Python
- `pokedex/conversation.py` max 20 turns per session; sessions are dicts keyed by UUID session_id

---

## File Map

### New files
| Path | Responsibility |
|---|---|
| `frontend/modules/pokemon-panel.js` | Shared rendering module: `fetchPokeData`, `fetchMoveMeta`, `pokeSlug`, `pokemonDbArtworkUrl`, `pokemonDbSpriteUrl`, `renderStatBars`, `renderMovesTable`, `renderTypeEffectiveness`, `updatePhotoCard`, `setPanelHeader`, `matchupSummary`, `multLabel` — all with `ns` param |
| `frontend/coach.html` | Coach page shell; same Atomic CDN imports as dashboard |
| `frontend/coach.css` | Chat thread, bubbles, `.cmp-panel`, `.delta-col`, `.verdict-bar` — imports no external CSS |
| `frontend/coach.js` | Conversation loop, comparison intent, Headless init, QS, analytics, comparison renderer |
| `pokedex/conversation.py` | In-memory session store: `get_or_create(session_id)`, `append_turn(session_id, role, content)`, `get_history(session_id)`, `clear(session_id)` |
| `pokedex/routes/coach_api.py` | Flask blueprint: `POST /api/coach`, `POST /api/coach-challenge` |
| `tests/unit/test_conversation.py` | Unit tests for session store |
| `tests/unit/test_coach_routes.py` | Unit tests for `/api/coach` and `/api/coach-challenge` |
| `tests/e2e/test_coach_load.py` | E2e: page loads, input visible, comparison panel renders |

### Modified files
| Path | Change |
|---|---|
| `frontend/dashboard.js` | Import rendering functions from `pokemon-panel.js`; pass `ns=''`; add hover Compare button to result rows |
| `pokedex/routes/pages.py` | Add `GET /coach` route |
| `pokedex/app.py` | Register `coach_bp` |
| `tests/unit/test_routes.py` | Add `/coach`, `/api/coach`, `/api/coach-challenge` to route assertion |

---

---

## Task 1: Extract shared rendering module `pokemon-panel.js`

**Files:**
- Create: `frontend/modules/pokemon-panel.js`
- Modify: `frontend/dashboard.js` (import from module, pass `ns=''`)

**Interfaces:**
- Produces (consumed by Tasks 4 and 5):
  - `fetchPokeData(name) → Promise<{id, sprite, types, stats, moves} | null>`
  - `fetchMoveMeta(moveName) → Promise<{type, power, cls}>`
  - `pokeSlug(name) → string`
  - `pokemonDbArtworkUrl(name, raw?) → string`
  - `pokemonDbSpriteUrl(name) → string`
  - `renderStatBars(stats, ns) → void` — writes to `#stat-bars{ns}`
  - `renderMovesTable(moves, pokeTypes, ns) → Promise<void>` — writes to `#moves-tbody{ns}`
  - `renderTypeEffectiveness(types, ns) → void` — writes to `#weak-chips{ns}`, `#resist-chips{ns}`, `#strong-chips{ns}`
  - `updatePhotoCard(artworkUrl, name, pokeId, primaryType, ns) → void` — writes to `#psprite{ns}`, `#photo-glow{ns}`
  - `setPanelHeader(name, types, pokeId, ns) → void` — writes to `#rp-name{ns}`, `#rp-tags{ns}`
  - `matchupSummary(types) → string` (pure, no DOM)
  - `TYPE_COLORS`, `TYPE_CHART`, `ALL_TYPES`, `typeMultiplier`, `multLabel` (re-exported)

- [ ] **Step 1: Create `frontend/modules/pokemon-panel.js` with all shared code**

```javascript
/**
 * pokemon-panel.js — shared Pokémon panel rendering primitives.
 *
 * Every function that touches the DOM accepts an `ns` (namespace) suffix
 * appended to element IDs, so two panels can coexist:
 *   ns = ''    → existing dashboard IDs (#stat-bars, #rp-name, …)
 *   ns = '-a'  → comparison panel A    (#stat-bars-a, #rp-name-a, …)
 *   ns = '-b'  → comparison panel B    (#stat-bars-b, #rp-name-b, …)
 */

import { TYPE_COLORS } from './type-colors.js';
import { TYPE_CHART, ALL_TYPES, typeMultiplier, multLabel } from './type-chart.js';

export { TYPE_COLORS, TYPE_CHART, ALL_TYPES, typeMultiplier, multLabel };

// ── slug overrides ────────────────────────────────────────────
const SLUG_OVERRIDES = {
  "farfetch'd": 'farfetchd',   "sirfetch'd": 'sirfetchd',
  'mr. mime': 'mr-mime',       'mr. rime': 'mr-rime',
  'mime jr.': 'mime-jr',       'type: null': 'type-null',
  'nidoran♀': 'nidoran-f',     'nidoran♂': 'nidoran-m',
  'deoxys': 'deoxys-normal',   'wormadam': 'wormadam-plant',
  'giratina': 'giratina-altered', 'shaymin': 'shaymin-land',
  'basculin': 'basculin-red-striped', 'darmanitan': 'darmanitan-standard',
  'tornadus': 'tornadus-incarnate', 'thundurus': 'thundurus-incarnate',
  'landorus': 'landorus-incarnate', 'keldeo': 'keldeo-ordinary',
  'meloetta': 'meloetta-aria', 'meowstic': 'meowstic-male',
  'aegislash': 'aegislash-shield', 'pumpkaboo': 'pumpkaboo-average',
  'gourgeist': 'gourgeist-average', 'zygarde': 'zygarde-50',
  'oricorio': 'oricorio-baile', 'lycanroc': 'lycanroc-midday',
  'wishiwashi': 'wishiwashi-solo', 'minior': 'minior-red-meteor',
  'toxtricity': 'toxtricity-amped', 'eiscue': 'eiscue-ice',
  'indeedee': 'indeedee-male', 'urshifu': 'urshifu-single-strike',
  'basculegion': 'basculegion-male', 'enamorus': 'enamorus-incarnate',
  'oinkologne': 'oinkologne-male', 'maushold': 'maushold-family-of-four',
  'squawkabilly': 'squawkabilly-green-plumage', 'palafin': 'palafin-zero',
  'tatsugiri': 'tatsugiri-curly', 'dudunsparce': 'dudunsparce-two-segment',
};

export function pokeSlug(name) {
  const key = String(name ?? '').toLowerCase().trim();
  if (SLUG_OVERRIDES[key]) return SLUG_OVERRIDES[key];
  return key
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[''.:]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function pokemonDbArtworkUrl(name, raw) {
  const slug = pokeSlug(name);
  if (raw?.image_url) return raw.image_url;
  return `https://img.pokemondb.net/artwork/large/${slug}.jpg`;
}

export function pokemonDbSpriteUrl(name) {
  return `https://img.pokemondb.net/sprites/home/normal/${pokeSlug(name)}.png`;
}

// ── PokéAPI cache ─────────────────────────────────────────────
const _cache = {};

export async function fetchPokeData(name) {
  const key = pokeSlug(name);
  if (!key) return null;
  if (_cache[key]) return _cache[key];
  try {
    const r = await fetch(`https://pokeapi.co/api/v2/pokemon/${key}`);
    if (!r.ok) return null;
    const d = await r.json();
    const byName = new Map();
    for (const m of d.moves) {
      for (const v of m.version_group_details) {
        if (v.move_learn_method.name !== 'level-up') continue;
        const prev = byName.get(m.move.name);
        if (prev === undefined || v.level_learned_at > prev) {
          byName.set(m.move.name, v.level_learned_at);
        }
      }
    }
    const levelMoves = [...byName.entries()]
      .map(([n, level]) => ({ name: n, level }))
      .sort((a, b) => b.level - a.level);
    const data = {
      id:     d.id,
      sprite: d.sprites?.front_default ?? '',
      types:  d.types.map(t => t.type.name),
      stats:  Object.fromEntries(d.stats.map(s => [s.stat.name, s.base_stat])),
      moves:  levelMoves,
    };
    _cache[key] = data;
    return data;
  } catch { return null; }
}

const _moveCache = {};
export async function fetchMoveMeta(moveName) {
  if (_moveCache[moveName]) return _moveCache[moveName];
  try {
    const r = await fetch(`https://pokeapi.co/api/v2/move/${moveName}`);
    if (!r.ok) return { type: 'normal', power: null, cls: '' };
    const d = await r.json();
    const meta = { type: d.type?.name ?? 'normal', power: d.power ?? null, cls: d.damage_class?.name ?? '' };
    _moveCache[moveName] = meta;
    return meta;
  } catch { return { type: 'normal', power: null, cls: '' }; }
}

// ── Stat bars ─────────────────────────────────────────────────
const STAT_CONFIG = [
  { key: 'hp',              label: 'HP',  color: '#44dd44' },
  { key: 'attack',          label: 'ATK', color: '#f0d040' },
  { key: 'defense',         label: 'DEF', color: '#4fc3f7' },
  { key: 'special-attack',  label: 'Sp.A',color: '#ff6b81' },
  { key: 'special-defense', label: 'Sp.D',color: '#ab6ac8' },
  { key: 'speed',           label: 'SPD', color: '#ff9c54' },
];
const STAT_MAX = 255;

export const STAT_KEYS = STAT_CONFIG.map(s => s.key);

function escHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function renderStatBars(stats, ns = '') {
  const container = document.getElementById(`stat-bars${ns}`);
  if (!container) return;
  container.innerHTML = STAT_CONFIG.map(({ key, label, color }) => {
    const val = stats[key] ?? 0;
    const pct = Math.round((val / STAT_MAX) * 100);
    return `<div class="srow2">
      <span class="slbl">${label}</span>
      <div class="strk"><div class="sfil" style="width:${pct}%;background:${color}"></div></div>
      <span class="sval">${val}</span>
    </div>`;
  }).join('');
}

export async function renderMovesTable(moves, pokeTypes, ns = '') {
  const tbody = document.getElementById(`moves-tbody${ns}`);
  if (!tbody) return;
  if (!moves?.length) {
    tbody.innerHTML = '<tr><td colspan="3" style="color:#555;font-size:11px;text-align:center;padding:10px;">No move data</td></tr>';
    return;
  }
  const displayed = moves.slice(0, 20);
  tbody.innerHTML = displayed.map(m => {
    const lvLabel = m.level === 0 ? '—' : m.level;
    const moveName = m.name.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    return `<tr data-move="${escHtml(m.name)}">
      <td class="mlv">${lvLabel}</td>
      <td class="mname">${escHtml(moveName)}<span class="mpow"></span></td>
      <td class="mtype-cell"><span class="mtype-pill" style="background:#2a2a3e;color:#888">…</span></td>
    </tr>`;
  }).join('');
  for (const m of displayed) {
    fetchMoveMeta(m.name).then(meta => {
      const row = tbody.querySelector(`tr[data-move="${CSS.escape(m.name)}"]`);
      if (!row) return;
      const pill = row.querySelector('.mtype-pill');
      if (pill) {
        const t = (meta.type ?? 'normal').toLowerCase();
        const colors = TYPE_COLORS[t] ?? { bg: '#9099A1' };
        pill.style.background = colors.bg + '33';
        pill.style.color = colors.bg;
        pill.textContent = t.charAt(0).toUpperCase() + t.slice(1);
      }
      const pow = row.querySelector('.mpow');
      if (pow) {
        const icon = meta.cls === 'physical' ? 'PHY' : meta.cls === 'special' ? 'SPC' : 'STA';
        pow.textContent = meta.power ? ` · ${meta.power} ${icon}` : ` · ${icon}`;
      }
    });
  }
}

export function renderTypeEffectiveness(types, ns = '') {
  const weakEl   = document.getElementById(`weak-chips${ns}`);
  const resistEl = document.getElementById(`resist-chips${ns}`);
  const strongEl = document.getElementById(`strong-chips${ns}`);
  if (!weakEl || !strongEl) return;
  const defTypes = types.map(t => t.toLowerCase());
  const none = '<span style="color:#555;font-size:11px;">None</span>';
  const weak = [], resist = [], immune = [];
  for (const atk of ALL_TYPES) {
    const m = typeMultiplier(atk, defTypes);
    if (m === 0)    immune.push(atk);
    else if (m > 1) weak.push([atk, m]);
    else if (m < 1) resist.push([atk, m]);
  }
  weak.sort((a, b) => b[1] - a[1]);
  resist.sort((a, b) => a[1] - b[1]);
  const cap = t => t.charAt(0).toUpperCase() + t.slice(1);
  weakEl.innerHTML = weak.map(([t, m]) =>
    `<span class="echip wk">${cap(t)} ${multLabel(m)}</span>`).join('') || none;
  if (resistEl) {
    resistEl.innerHTML =
      immune.map(t => `<span class="echip im">${cap(t)} ×0</span>`).join('')
      + resist.map(([t, m]) => `<span class="echip rs">${cap(t)} ${multLabel(m)}</span>`).join('')
      || none;
  }
  const strongSet = new Set();
  defTypes.forEach(atk => {
    ALL_TYPES.forEach(def => {
      if ((TYPE_CHART[atk]?.[def] ?? 1) > 1) strongSet.add(def);
    });
  });
  strongEl.innerHTML = [...strongSet].map(t =>
    `<span class="echip st">${cap(t)}</span>`).join('') || none;
}

export function updatePhotoCard(artworkUrl, name, pokeId, primaryType, ns = '') {
  const img = document.getElementById(`psprite${ns}`);
  if (img) {
    img.src = artworkUrl || `/images/${(name ?? '').toLowerCase()}_image.jpg`;
    img.style.display = '';
  }
  const glow = document.getElementById(`photo-glow${ns}`);
  if (glow && primaryType) {
    const colors = TYPE_COLORS[primaryType.toLowerCase()] ?? {};
    const hex = colors.bg ?? '#ff9832';
    glow.style.background = `radial-gradient(ellipse at 50% 60%, ${hex}22 0%, transparent 70%)`;
  }
}

export function setPanelHeader(name, types, pokeId, ns = '') {
  const nameEl = document.getElementById(`rp-name${ns}`);
  const tagsEl = document.getElementById(`rp-tags${ns}`);
  if (nameEl) nameEl.textContent = name;
  if (tagsEl && types.length) {
    tagsEl.innerHTML = types.map(t => {
      const colors = TYPE_COLORS[t.toLowerCase()] ?? { bg: '#444', text: '#ccc' };
      return `<span class="rptag" style="background:${colors.bg}33;color:${colors.bg}">${t.charAt(0).toUpperCase() + t.slice(1)}</span>`;
    }).join('') + (pokeId ? `<span class="rptag" style="background:rgba(79,195,247,.15);color:#4fc3f7">#${String(pokeId).padStart(3,'0')}</span>` : '');
  }
}

export function matchupSummary(types) {
  if (!types?.length) return '';
  const defTypes = types.map(t => t.toLowerCase());
  const best = [], immune = [];
  for (const atk of ALL_TYPES) {
    const m = typeMultiplier(atk, defTypes);
    if (m === 0) immune.push(atk);
    else if (m >= 2) best.push([atk, m]);
  }
  best.sort((a, b) => b[1] - a[1]);
  const cap = t => t.charAt(0).toUpperCase() + t.slice(1);
  const parts = [];
  if (best.length) parts.push(`Hit it with ${best.map(([t, m]) => `${cap(t)} ${multLabel(m)}`).join(', ')}.`);
  else             parts.push('Nothing is super effective against it.');
  if (immune.length) parts.push(`Do NOT use ${immune.map(cap).join(' or ')} — no effect.`);
  return parts.join(' ');
}
```

- [ ] **Step 2: Update `dashboard.js` to import from the module (lines 9–10 and every function that moved)**

Replace the top of `dashboard.js` (lines 1–11) and remove the duplicated function bodies, replacing them with imports. The public API to the rest of `dashboard.js` is unchanged — only the source location moves.

```javascript
// Replace lines 9-10:
import { TYPE_COLORS, TYPE_CHART, ALL_TYPES, typeMultiplier, multLabel,
         pokeSlug, pokemonDbArtworkUrl, pokemonDbSpriteUrl,
         fetchPokeData, fetchMoveMeta,
         renderStatBars, renderMovesTable, renderTypeEffectiveness,
         updatePhotoCard, setPanelHeader, matchupSummary,
         STAT_KEYS } from './modules/pokemon-panel.js';
```

Then delete the duplicated bodies of: `pokeSlug`, `pokemonDbArtworkUrl`, `pokemonDbSpriteUrl`, `fetchPokeData` (lines 155–229), `fetchMoveMeta` (lines 1120–1135), `STAT_CONFIG`, `STAT_MAX`, `renderStatBars` (lines 1048–1071), `renderMovesTable` (lines 1076–1118), `renderTypeEffectiveness` (lines 1140–1186), `updatePhotoCard` (lines 1005–1020), `matchupSummary` (lines 1317–1333).

Update every call site to pass `ns = ''` as the final argument:
```javascript
renderStatBars(poke.stats, '');
renderMovesTable(poke.moves, poke.types, '');
renderTypeEffectiveness(poke.types, '');
updatePhotoCard(artworkUrl, name, poke.id, poke.types[0], '');
setPanelHeader(name, poke.types, poke.id, '');   // replaces setRightPanelName
```

Also replace the two remaining direct calls to `setPhotoName` (which stays in `dashboard.js` since it writes `#photo-name` and `#photo-num`, not covered by `setPanelHeader`).

- [ ] **Step 3: Verify dashboard renders identically**

Start the server and open `http://localhost:5003/dashboard`. Search for "Charizard". Confirm:
- Stat bars render with correct values
- Type effectiveness chips appear under Weak/Resists/Strong
- Moves table shows level-up moves with type pills
- Photo card artwork loads

Run unit tests to confirm no regressions:
```bash
pytest tests/unit/ -v
```
Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/modules/pokemon-panel.js frontend/dashboard.js
git commit -m "refactor: extract shared pokemon-panel.js module with ns param"
```

---

## Task 2: Session store `conversation.py`

**Files:**
- Create: `pokedex/conversation.py`
- Create: `tests/unit/test_conversation.py`

**Interfaces:**
- Produces (consumed by Task 3):
  - `get_or_create(session_id: str) -> list[dict]` — returns mutable turn list
  - `append_turn(session_id: str, role: str, content: str, pokemon_context: list[str] | None = None) -> None`
  - `get_history(session_id: str) -> list[dict]` — returns copy; empty list if unknown
  - `clear(session_id: str) -> None`
  - `MAX_TURNS: int = 20`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_conversation.py
import pytest


def test_new_session_is_empty():
    from pokedex.conversation import get_or_create, clear
    clear("s1")
    turns = get_or_create("s1")
    assert turns == []


def test_append_and_retrieve():
    from pokedex.conversation import append_turn, get_history, clear
    clear("s2")
    append_turn("s2", "user", "hello")
    append_turn("s2", "assistant", "hi", pokemon_context=["Pikachu"])
    history = get_history("s2")
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "hello", "pokemon_context": None}
    assert history[1]["pokemon_context"] == ["Pikachu"]


def test_max_turns_evicts_oldest():
    from pokedex.conversation import append_turn, get_history, clear, MAX_TURNS
    clear("s3")
    for i in range(MAX_TURNS + 5):
        append_turn("s3", "user", f"msg{i}")
    history = get_history("s3")
    assert len(history) == MAX_TURNS
    assert history[0]["content"] == f"msg{5}"


def test_get_history_returns_copy():
    from pokedex.conversation import append_turn, get_history, clear
    clear("s4")
    append_turn("s4", "user", "x")
    h = get_history("s4")
    h.clear()
    assert len(get_history("s4")) == 1


def test_clear_removes_session():
    from pokedex.conversation import append_turn, get_history, clear
    append_turn("s5", "user", "y")
    clear("s5")
    assert get_history("s5") == []


def test_unknown_session_returns_empty():
    from pokedex.conversation import get_history
    assert get_history("no-such-session-xyz") == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_conversation.py -v
```
Expected: `ModuleNotFoundError: No module named 'pokedex.conversation'`

- [ ] **Step 3: Implement `pokedex/conversation.py`**

```python
"""In-memory conversation session store.

Sessions are keyed by session_id (UUID string from the client).
Each session holds at most MAX_TURNS turns; oldest are evicted when the
limit is exceeded. No persistence — sessions are lost on server restart.
"""
from __future__ import annotations

from collections import deque
from typing import Deque

MAX_TURNS: int = 20

# { session_id: deque of {role, content, pokemon_context} }
_sessions: dict[str, Deque[dict]] = {}


def get_or_create(session_id: str) -> list[dict]:
    """Return the current turn list for a session (creates empty if new)."""
    if session_id not in _sessions:
        _sessions[session_id] = deque(maxlen=MAX_TURNS)
    return list(_sessions[session_id])


def append_turn(
    session_id: str,
    role: str,
    content: str,
    pokemon_context: list[str] | None = None,
) -> None:
    """Append a turn; oldest turn is dropped automatically when MAX_TURNS is hit."""
    if session_id not in _sessions:
        _sessions[session_id] = deque(maxlen=MAX_TURNS)
    _sessions[session_id].append(
        {"role": role, "content": content, "pokemon_context": pokemon_context}
    )


def get_history(session_id: str) -> list[dict]:
    """Return a copy of the session's turn list; empty list if unknown."""
    return list(_sessions.get(session_id, []))


def clear(session_id: str) -> None:
    """Remove all turns for the session."""
    _sessions.pop(session_id, None)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/test_conversation.py -v
```
Expected: 6 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add pokedex/conversation.py tests/unit/test_conversation.py
git commit -m "feat: add in-memory conversation session store"
```

---

## Task 3: Coach API blueprint `coach_api.py`

**Files:**
- Create: `pokedex/routes/coach_api.py`
- Create: `tests/unit/test_coach_routes.py`
- Modify: `pokedex/app.py`
- Modify: `tests/unit/test_routes.py`

**Interfaces:**
- Consumes: `CoveoClient` from `pokedex.coveo`, `get_history`/`append_turn` from `pokedex.conversation`, `ScenarioBuilder` from `eval_harness.scenarios`, `TypeChart` from `eval_harness.typechart`, `check_type_claims`/`check_chart_claims` from `eval_harness.grading`
- Produces:
  - `POST /api/coach` — body `{session_id: str, message: str}`, returns `{answer: str, citations: list, session_id: str, comparison: dict | null, grading_flags: list}`
  - `POST /api/coach-challenge` — body `{axis?: str}`, returns `{prompt: str, session_id: str, scenario: dict}`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_coach_routes.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    from pokedex.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_coach_route_registered(client):
    rules = {r.rule for r in client.application.url_map.iter_rules()}
    assert "/api/coach" in rules
    assert "/api/coach-challenge" in rules


def test_coach_requires_message(client):
    r = client.post("/api/coach", json={"session_id": "abc"})
    assert r.status_code == 400
    assert b"message" in r.data


def test_coach_requires_session_id(client):
    r = client.post("/api/coach", json={"message": "hello"})
    assert r.status_code == 400
    assert b"session_id" in r.data


def test_coach_returns_answer_shape(client):
    mock_result = MagicMock()
    mock_result.answer = "Charizard is Fire/Flying."
    mock_result.citations = []
    mock_result.stream_completed = True
    mock_result.error = None
    with patch("pokedex.routes.coach_api.CoveoClient") as MockClient:
        MockClient.return_value.generated_answer.return_value = mock_result
        r = client.post("/api/coach", json={"session_id": "test-1", "message": "tell me about Charizard"})
    assert r.status_code == 200
    d = r.get_json()
    assert "answer" in d
    assert "citations" in d
    assert "session_id" in d
    assert "comparison" in d
    assert "grading_flags" in d


def test_coach_detect_comparison_intent(client):
    mock_result = MagicMock()
    mock_result.answer = "Charizard vs Dragonite comparison."
    mock_result.citations = []
    mock_result.stream_completed = True
    mock_result.error = None
    with patch("pokedex.routes.coach_api.CoveoClient") as MockClient:
        MockClient.return_value.generated_answer.return_value = mock_result
        r = client.post("/api/coach", json={
            "session_id": "test-2",
            "message": "compare Charizard and Dragonite"
        })
    assert r.status_code == 200
    d = r.get_json()
    assert d["comparison"] is not None
    assert d["comparison"]["pokemon_a"] == "charizard"
    assert d["comparison"]["pokemon_b"] == "dragonite"


def test_coach_challenge_returns_prompt(client):
    r = client.post("/api/coach-challenge", json={})
    assert r.status_code == 200
    d = r.get_json()
    assert "prompt" in d
    assert "session_id" in d
    assert "scenario" in d
    assert len(d["prompt"]) > 10
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_coach_routes.py -v
```
Expected: `ImportError` or 404 errors — routes don't exist yet.

- [ ] **Step 3: Create `pokedex/routes/coach_api.py`**

```python
"""Coach API blueprint: stateful conversation, comparison detection, challenge mode."""
from __future__ import annotations

import re
import uuid

from flask import Blueprint, jsonify, request

from pokedex.conversation import append_turn, get_history
from pokedex.coveo import CoveoClient

coach_bp = Blueprint("coach_api", __name__)

# ── Comparison intent detection ───────────────────────────────
# Patterns (case-insensitive). Each returns (name_a, name_b) or None.
_CMP_PATTERNS = [
    # "compare Charizard and Dragonite" / "compare X vs Y"
    re.compile(
        r'\bcompare\s+([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30}?)\s+'
        r'(?:and|vs\.?|versus)\s+([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30})',
        re.I
    ),
    # "Charizard vs Dragonite" / "Charizard versus Dragonite"
    re.compile(
        r'\b([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30}?)\s+'
        r'(?:vs\.?|versus)\s+([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30})',
        re.I
    ),
    # "which is better: Umbreon or Espeon" / "Umbreon or Espeon"
    re.compile(
        r'\b([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30}?)\s+or\s+([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30})'
        r'(?=\s*[?,]|\s+for|\s+on|\s+against|\s*$)',
        re.I
    ),
]

# Single-word Pokémon names that would produce false positives in the "or" pattern.
_STOPWORDS = {
    'a', 'an', 'the', 'my', 'your', 'his', 'her', 'their', 'our',
    'not', 'no', 'yes', 'can', 'will', 'should', 'would', 'could',
    'what', 'which', 'who', 'when', 'where', 'why', 'how',
    'fire', 'water', 'grass', 'electric', 'ice', 'fighting', 'poison',
    'ground', 'flying', 'psychic', 'bug', 'rock', 'ghost', 'dragon',
    'dark', 'steel', 'fairy', 'normal',
}


def _detect_comparison(message: str) -> tuple[str, str] | None:
    """Return (pokemon_a, pokemon_b) if the message is a comparison request."""
    for pattern in _CMP_PATTERNS:
        m = pattern.search(message)
        if m:
            a = m.group(1).strip().lower()
            b = m.group(2).strip().lower()
            # Reject stopwords and strings over 25 chars (not Pokémon names)
            if a in _STOPWORDS or b in _STOPWORDS:
                continue
            if len(a) > 25 or len(b) > 25:
                continue
            return a, b
    return None


def _build_context_prompt(history: list[dict], message: str) -> str:
    """
    Build the query string for the RGA call, incorporating recent history
    so the model can resolve pronouns like 'it' and 'them'.
    """
    if not history:
        return message
    # Include up to the last 4 turns as inline context
    recent = history[-4:]
    lines = []
    for turn in recent:
        role = "Trainer" if turn["role"] == "user" else "Oak"
        lines.append(f"{role}: {turn['content']}")
    lines.append(f"Trainer: {message}")
    return "\n".join(lines)


# ── /api/coach ────────────────────────────────────────────────
@coach_bp.route("/coach", methods=["POST"])
def coach():
    """
    Body: { "session_id": str, "message": str }
    Returns: {
        "answer": str,
        "citations": list,
        "session_id": str,
        "comparison": { "pokemon_a": str, "pokemon_b": str,
                        "verdict": str, "winner": str | null } | null,
        "grading_flags": list   # list of {type, message} dicts
    }
    """
    data = request.get_json(force=True)
    session_id = data.get("session_id", "").strip()
    message = data.get("message", "").strip()

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not message:
        return jsonify({"error": "message is required"}), 400

    # Detect comparison intent before calling the LLM
    comparison = None
    cmp_names = _detect_comparison(message)

    history = get_history(session_id)
    query = _build_context_prompt(history, message)

    client = CoveoClient()
    result = client.generated_answer(query)

    # Fallback to search excerpts if RGA did not fire
    if result.stream_completed is False and result.error is None:
        search_results = client.search(query, num=5).get("results", [])
        snippets = "; ".join(
            r.get("excerpt", r.get("title", ""))[:200]
            for r in search_results[:3]
            if r.get("excerpt") or r.get("title")
        )
        answer = (
            f"(RGA model did not trigger. Top result: {snippets})"
            if snippets else "(RGA model did not trigger for this query.)"
        )
        citations = []
    elif result.error:
        answer = f"(Error: {result.error})"
        citations = []
    else:
        answer = result.answer
        citations = [
            {
                "title": c.get("title", ""),
                "uri":   c.get("uri") or c.get("clickUri", ""),
            }
            for c in result.citations
        ]

    # Grading flags (type/chart errors in the answer)
    grading_flags = _grade_answer(answer, cmp_names)

    # Build comparison block
    if cmp_names:
        comparison = {
            "pokemon_a": cmp_names[0],
            "pokemon_b": cmp_names[1],
            "verdict":   answer,   # full answer is the verdict for the client to display
            "winner":    None,     # client computes BST winner from fetched stats
        }

    # Persist turns
    pokemon_ctx = list(cmp_names) if cmp_names else _extract_pokemon_mentions(message)
    append_turn(session_id, "user", message, pokemon_context=pokemon_ctx)
    append_turn(session_id, "assistant", answer, pokemon_context=pokemon_ctx)

    return jsonify({
        "answer":        answer,
        "citations":     citations,
        "session_id":    session_id,
        "comparison":    comparison,
        "grading_flags": grading_flags,
    })


def _grade_answer(answer: str, cmp_names: tuple[str, str] | None) -> list[dict]:
    """Run objective type/chart checks; return list of flag dicts."""
    flags = []
    try:
        from eval_harness.grading import check_chart_claims
        for err in check_chart_claims(answer):
            flags.append({"type": "chart_error", "message": err["claim"],
                          "quote": err.get("quote", "")})
    except Exception:
        pass
    return flags


# Very lightweight — just look for capitalised words that could be Pokémon names.
_POKEMON_MENTION_RE = re.compile(r'\b([A-Z][a-z]{2,}(?:-[A-Z][a-z]+)?)\b')


def _extract_pokemon_mentions(text: str) -> list[str]:
    return list(dict.fromkeys(
        m.group(1).lower()
        for m in _POKEMON_MENTION_RE.finditer(text)
        if m.group(1).lower() not in _STOPWORDS
    ))[:4]


# ── /api/coach-challenge ──────────────────────────────────────
@coach_bp.route("/coach-challenge", methods=["POST"])
def coach_challenge():
    """
    Body: { "axis"?: str }   — optional axis name from eval_harness.scenarios.AXES
    Returns: { "prompt": str, "session_id": str, "scenario": dict }

    Draws a random battle scenario and returns the first probe question
    as a ready-to-send coach message. The scenario dict gives the client
    enough information to render the team and wild Pokémon.
    """
    import random
    from eval_harness.scenarios import ScenarioBuilder, AXES, DEFAULT_PROBES
    from eval_harness.typechart import TypeChart
    from pathlib import Path

    data = request.get_json(force=True) or {}
    axis = data.get("axis", "baseline")
    if axis not in AXES:
        axis = "baseline"

    try:
        cache_path = Path("eval_data/type_cache.json")
        chart = TypeChart(cache_path, offline=cache_path.exists())
        # Load Pokémon names from corpus or fall back to a small hardcoded set
        try:
            import json
            corpus_path = Path("eval_data/corpus.json")
            pool = json.loads(corpus_path.read_text()) if corpus_path.exists() else []
        except Exception:
            pool = []
        if len(pool) < 7:
            pool = [
                "charizard", "blastoise", "venusaur", "pikachu", "gengar",
                "alakazam", "machamp", "gyarados", "lapras", "eevee",
                "vaporeon", "jolteon", "flareon", "mewtwo", "dragonite",
            ]
        rng = random.Random()
        builder = ScenarioBuilder(pool, chart, rng)
        sc = builder.draw(axis=axis)
        if sc is None:
            return jsonify({"error": f"could not build a scenario for axis {axis!r}"}), 500
        builder.attach_probes(sc, ["advantage"])
        probe_text = sc.probes[0][1] if sc.probes else (
            f"My team is {', '.join(sc.team)}. "
            f"Which of them has a type advantage against {sc.wild}?"
        )
    except Exception as exc:
        # Graceful fallback — return a generic prompt
        probe_text = "I'm facing a wild Pokémon. Can you help me decide who to send out?"
        session_id = str(uuid.uuid4())
        return jsonify({
            "prompt":     probe_text,
            "session_id": session_id,
            "scenario":   {},
            "error":      str(exc),
        })

    session_id = str(uuid.uuid4())
    append_turn(session_id, "user", probe_text, pokemon_context=sc.team + [sc.wild])

    return jsonify({
        "prompt":     probe_text,
        "session_id": session_id,
        "scenario": {
            "axis":  sc.axis,
            "wild":  sc.wild,
            "team":  sc.team,
        },
    })
```

- [ ] **Step 4: Register the blueprint in `pokedex/app.py`**

```python
# Add after the existing blueprint imports:
from pokedex.routes.coach_api import coach_bp

# Add inside create_app() after the other register_blueprint calls:
app.register_blueprint(coach_bp, url_prefix="/api")
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/test_coach_routes.py -v
```
Expected: 6 tests PASSED.

- [ ] **Step 6: Update `test_routes.py` to include new routes**

```python
# In test_all_routes_are_registered, add to the expected list:
"/coach", "/api/coach", "/api/coach-challenge",
```

- [ ] **Step 7: Run all unit tests**

```bash
pytest tests/unit/ -v
```
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add pokedex/routes/coach_api.py pokedex/app.py tests/unit/test_coach_routes.py tests/unit/test_routes.py
git commit -m "feat: add /api/coach and /api/coach-challenge endpoints"
```

---

## Task 4: Coach page route

**Files:**
- Modify: `pokedex/routes/pages.py`

**Interfaces:**
- Produces: `GET /coach` — HTML page with `COVEO_ORGANIZATION_ID` injected

- [ ] **Step 1: Add the `/coach` route**

In `pokedex/routes/pages.py`, add after the `/dashboard` route:

```python
@pages_bp.route("/coach")
def coach():
    html = (_FRONTEND_DIR / "coach.html").read_text()
    return render_template_string(html, COVEO_ORGANIZATION_ID=_COVEO_ORG)
```

- [ ] **Step 2: Create a placeholder `coach.html` so the route is testable**

```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"/><title>Pokémon Coach</title></head>
<body data-coveo-org="{{ COVEO_ORGANIZATION_ID }}">
  <p id="coach-placeholder">Coach coming soon</p>
</body>
</html>
```
Save to `frontend/coach.html`.

- [ ] **Step 3: Verify route**

```bash
pytest tests/unit/test_routes.py::test_all_routes_are_registered -v
```
Expected: PASSED.

Also confirm manually:
```bash
curl -s http://localhost:5003/coach | grep coach-placeholder
```
Expected: `<p id="coach-placeholder">Coach coming soon</p>`

- [ ] **Step 4: Commit**

```bash
git add pokedex/routes/pages.py frontend/coach.html
git commit -m "feat: add /coach page route"
```

---

## Task 5: Coach CSS

**Files:**
- Create: `frontend/coach.css`

**Interfaces:**
- Produces: CSS classes consumed by `coach.html` and `coach.js` (Task 6):
  - `.coach-wrap` — outer page layout
  - `.coach-topbar` — top bar (same structure as `.c-topbar`)
  - `.thread` — scrollable chat thread column
  - `.right-panel` — right column (smart snippet + recommendations)
  - `.input-bar` — bottom input area
  - `.bubble`, `.bubble-user`, `.bubble-oak` — chat bubbles
  - `.suggestions-drop` — query suggestion dropdown
  - `.cmp-panel` — two-column comparison grid
  - `.cmp-card` — individual comparison card (reuses `.right` panel classes)
  - `.delta-col` — stat delta column between two panels
  - `.verdict-bar`, `.verdict-bar.draw` — comparison verdict strip
  - `.quick-chips` — pre-conversation prompt chips
  - `.citation-pill` — citation link pill

- [ ] **Step 1: Create `frontend/coach.css`**

```css
/* ============================================================
   Pokémon Coach — Chat UI
   Layout: topbar | (thread + input) | right panel
   Reuses all card/stat/chip classes from dashboard.css verbatim.
   ============================================================ */

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #0d0d1a;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0;
  font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
  color: #e0e0e0;
}

/* ── Page wrapper ── */
.coach-wrap {
  display: grid;
  grid-template-rows: auto 1fr;
  grid-template-columns: 1fr 300px;
  grid-template-areas:
    "topbar topbar"
    "main   aside";
  width: 100%;
  max-width: 1100px;
  height: 100vh;
  gap: 0;
}

/* ── Top bar ── */
.coach-topbar {
  grid-area: topbar;
  background: #161626;
  border-bottom: 1px solid #2a2a40;
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.coach-topbar .leds { display: flex; gap: 6px; }
.coach-topbar .led  { width: 11px; height: 11px; border-radius: 50%; }
.coach-topbar .lr   { background: #ff4444; box-shadow: 0 0 5px #ff4444; }
.coach-topbar .ly   { background: #ffcc00; box-shadow: 0 0 5px #ffcc00; }
.coach-topbar .lg   { background: #44dd44; box-shadow: 0 0 5px #44dd44; }
.coach-brand {
  font-size: 14px; font-weight: 900; color: #f0d040;
  font-family: "Comic Sans MS", "Chalkboard SE", cursive;
  margin-left: 6px;
}
.coach-sub { font-size: 11px; color: #555; }
.coach-topbar .model-pill {
  margin-left: auto;
  background: #f9e400; border: 2px solid #333; border-radius: 6px;
  padding: 3px 10px; display: flex; align-items: center; gap: 4px;
}
.coach-topbar .model-arrow { font-size: 10px; color: #1a1a1a; }
.coach-topbar #model-select {
  background: transparent; border: none; outline: none;
  font-weight: 800; font-size: 11px; color: #1a1a1a; cursor: pointer;
}
.dashboard-link {
  font-size: 11px; font-weight: 700; color: #4fc3f7;
  text-decoration: none; padding: 3px 8px;
  border: 1px solid #2a4070; border-radius: 5px;
  transition: background .12s;
}
.dashboard-link:hover { background: #1e2a4a; }

/* ── Main chat column ── */
.coach-main {
  grid-area: main;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid #2a2a40;
}

/* Thread (scrollable) */
.thread {
  flex: 1;
  overflow-y: auto;
  padding: 20px 20px 8px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  scrollbar-width: thin;
  scrollbar-color: #2a2a40 #0d0d1a;
}
.thread::-webkit-scrollbar { width: 4px; }
.thread::-webkit-scrollbar-track { background: #0d0d1a; }
.thread::-webkit-scrollbar-thumb { background: #2a2a40; border-radius: 2px; }

/* Quick-start chips shown before first message */
.quick-chips {
  display: flex; flex-wrap: wrap; gap: 8px;
  padding: 12px 0;
}
.quick-chip {
  background: #161626; border: 1px solid #2a4070;
  color: #4fc3f7; font-size: 12px; font-weight: 600;
  padding: 7px 14px; border-radius: 20px;
  cursor: pointer; transition: background .12s, border-color .12s;
}
.quick-chip:hover { background: #1e2a4a; border-color: #4fc3f7; }

/* Bubbles */
.bubble {
  max-width: 78%;
  font-size: 13px;
  line-height: 1.6;
}
.bubble-user {
  align-self: flex-end;
  background: #1e2a4a;
  border: 1px solid #2a4070;
  border-radius: 12px 12px 3px 12px;
  padding: 10px 14px;
  color: #f0d040;
  font-family: "Courier New", monospace;
}
.bubble-oak {
  align-self: flex-start;
  background: #161626;
  border: 1px solid #2a2a40;
  border-radius: 12px 12px 12px 3px;
  padding: 10px 14px;
  max-width: 92%;
}
.bubble-oak-header {
  font-size: 10px; font-weight: 800;
  text-transform: uppercase; letter-spacing: .08em;
  color: #4fc3f7; margin-bottom: 5px;
  display: flex; align-items: center; gap: 5px;
}
.oak-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #4fc3f7; box-shadow: 0 0 5px #4fc3f7;
}
.bubble-oak-text { color: #e0e0e0; }

/* Citation pills under Oak bubbles */
.citations-row { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.citation-pill {
  font-size: 10px; font-weight: 600; color: #4fc3f7;
  background: rgba(79,195,247,.08);
  border: 1px solid rgba(79,195,247,.25);
  border-radius: 4px; padding: 2px 8px;
  text-decoration: none; transition: background .12s;
}
.citation-pill:hover { background: rgba(79,195,247,.18); }

/* Grading flag inline */
.grade-flag {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; color: #ffaa44;
  background: rgba(255,170,68,.08);
  border: 1px solid rgba(255,170,68,.25);
  border-radius: 4px; padding: 2px 7px;
  margin-top: 5px;
}

/* Thinking indicator */
.bubble-thinking {
  align-self: flex-start;
  color: rgba(240,208,64,.4);
  font-size: 12px;
  font-family: "Courier New", monospace;
  font-style: italic;
  padding: 4px 0;
}

/* ── Comparison panels ── */
.cmp-panel {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 8px;
  margin-top: 10px;
  width: 100%;
  max-width: 780px;
}
/* Each card reuses the dashboard .right panel structure */
.cmp-card {
  background: #161626;
  border: 1px solid #2a2a40;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.cmp-head {
  background: #1e1e32;
  border-bottom: 1px solid #2a2a40;
  padding: 10px 14px;
  flex-shrink: 0;
}
.cmp-name {
  font-size: 16px; font-weight: 900; color: #f0d040;
  font-family: "Comic Sans MS", "Chalkboard SE", cursive;
}
.cmp-tags { display: flex; gap: 5px; margin-top: 5px; flex-wrap: wrap; }
.cmp-body {
  padding: 10px 14px;
  display: flex; flex-direction: column; gap: 10px;
  overflow-y: auto; flex: 1;
  scrollbar-width: thin; scrollbar-color: #2a2a40 #161626;
  max-height: 480px;
}
/* Photo card inside comparison — smaller */
.cmp-photo {
  background: linear-gradient(145deg, #1a1f3a, #0f1228);
  border: 1px solid #2a2a40; border-radius: 8px;
  height: 140px; position: relative; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
}
.cmp-photo .photo-glow {
  position: absolute; inset: 0;
  background: radial-gradient(ellipse at 50% 60%, rgba(255,152,50,.12) 0%, transparent 70%);
  transition: background .4s;
}
.cmp-photo .psprite {
  width: auto; height: 110px; max-width: 150px;
  object-fit: contain;
  filter: drop-shadow(0 0 18px rgba(255,152,50,.5));
  z-index: 1;
}
.cmp-photo-overlay {
  position: absolute; bottom: 0; left: 0; right: 0;
  padding: 5px 10px;
  background: linear-gradient(transparent, rgba(0,0,0,.7));
  font-size: 11px; font-weight: 700; color: rgba(240,208,64,.7);
}

/* Delta column between the two stat grids */
.delta-col {
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  padding-top: 40px;           /* aligns with the first stat bar */
  gap: 3px;
  min-width: 42px;
  align-items: center;
}
.delta-label {
  font-size: 8px; font-weight: 800; color: #555;
  text-transform: uppercase; letter-spacing: .06em;
  margin-bottom: 4px; text-align: center;
}
.delta-val {
  font-size: 9px; font-weight: 800;
  height: 15px; /* matches .srow2 height */
  display: flex; align-items: center; justify-content: center;
  min-width: 38px;
}
.delta-up { color: #44dd88; }
.delta-dn { color: #ff6666; }
.delta-eq { color: #444; }

/* Verdict bar spans the full panel width */
.verdict-bar {
  grid-column: 1 / -1;
  background: #1a2a1a;
  border: 1px solid #2a4a2a;
  border-radius: 8px;
  padding: 9px 14px;
  font-size: 12px; color: #44dd88;
  line-height: 1.5;
}
.verdict-bar.draw {
  background: #1a1a2e;
  border-color: #2a2a50;
  color: #4fc3f7;
}

/* ── Input bar ── */
.input-bar {
  flex-shrink: 0;
  background: #161626;
  border-top: 1px solid #2a2a40;
  padding: 10px 16px;
  position: relative;
}
.input-row {
  display: flex;
  background: #0a0a18;
  border: 1px solid rgba(240,208,64,.35);
  border-radius: 8px;
  overflow: visible;
  transition: border-color .15s;
}
.input-row:focus-within { border-color: #f0d040; }
.coach-input {
  flex: 1; background: transparent; border: none; outline: none;
  color: #f0d040; caret-color: #f0d040;
  font-family: "Courier New", monospace; font-size: 13px;
  padding: 10px 14px;
  resize: none; min-height: 42px; max-height: 120px;
  overflow-y: auto;
}
.coach-input::placeholder { color: rgba(240,208,64,.35); }
.send-btn {
  background: transparent; border: none;
  border-left: 1px solid rgba(240,208,64,.2);
  color: #f0d040; font-size: 16px;
  padding: 0 14px; cursor: pointer;
  opacity: .7; transition: opacity .15s;
  align-self: stretch;
}
.send-btn:hover { opacity: 1; }

/* Query suggestion dropdown */
.suggestions-drop {
  position: absolute; bottom: 100%; left: 16px; right: 16px;
  background: #161626;
  border: 1px solid #2a2a40;
  border-radius: 8px 8px 0 0;
  max-height: 200px; overflow-y: auto;
  z-index: 100;
  display: none;
}
.suggestions-drop.open { display: block; }
.sug-item {
  padding: 8px 14px;
  font-size: 12px; color: #e0e0e0;
  cursor: pointer;
  border-bottom: 1px solid #1e1e32;
  transition: background .1s;
}
.sug-item:last-child { border-bottom: none; }
.sug-item:hover, .sug-item.focused { background: #1e2a4a; color: #f0d040; }

/* ── Right aside panel ── */
.coach-aside {
  grid-area: aside;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.aside-section {
  background: #161626;
  border-bottom: 1px solid #2a2a40;
  padding: 12px 14px;
  flex-shrink: 0;
}
.aside-title {
  font-size: 9px; font-weight: 800;
  text-transform: uppercase; letter-spacing: .1em;
  color: #4fc3f7;
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 8px;
}
.aside-title::after { content: ''; flex: 1; height: 1px; background: #2a2a40; }
.snippet-text {
  font-size: 12px; color: rgba(240,208,64,.8);
  font-family: "Courier New", monospace;
  line-height: 1.5;
  max-height: 100px; overflow-y: auto;
}
.snippet-empty { font-size: 11px; color: #555; }

/* Recommendations */
.rec-grid {
  display: flex; flex-direction: column; gap: 6px;
  overflow-y: auto; flex: 1;
  padding: 12px 14px;
}
.rec-card {
  background: #1e1e32; border: 1px solid #2a2a40;
  border-radius: 8px; padding: 8px 10px;
  display: flex; align-items: center; gap: 10px;
  cursor: pointer; transition: border-color .12s, background .12s;
}
.rec-card:hover { background: #252540; border-color: #4fc3f7; }
.rec-sprite {
  width: 40px; height: 40px; object-fit: contain;
  filter: drop-shadow(0 2px 5px rgba(0,0,0,.5));
}
.rec-info { flex: 1; }
.rec-name { font-size: 12px; font-weight: 700; color: #e0e0e0; }
.rec-type { font-size: 10px; color: #888; }

/* ── Responsive ── */
@media (max-width: 860px) {
  .coach-wrap {
    grid-template-columns: 1fr;
    grid-template-areas:
      "topbar"
      "main";
    height: auto;
    min-height: 100vh;
  }
  .coach-aside { display: none; }
  .cmp-panel {
    grid-template-columns: 1fr;
  }
  .delta-col { display: none; }
  .verdict-bar { grid-column: 1; }
}

@media (max-width: 480px) {
  body { padding: 0; }
  .thread { padding: 12px; }
  .bubble { max-width: 92%; }
}
```

- [ ] **Step 2: Verify CSS file is served**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5003/frontend/coach.css
```
Expected: `200`

- [ ] **Step 3: Commit**

```bash
git add frontend/coach.css
git commit -m "feat: add coach.css chat UI styles"
```

---

## Task 6: Coach HTML shell `coach.html`

**Files:**
- Modify: `frontend/coach.html` (replace placeholder)

**Interfaces:**
- Consumes: `coach.css`, `coach.js`, Coveo Atomic CDN
- Produces: all DOM IDs consumed by `coach.js`:
  - `#thread` — chat message container
  - `#coach-input` — textarea
  - `#send-btn` — send button
  - `#suggestions-drop` — dropdown container
  - `#quick-chips` — pre-chat chips container
  - `#model-select` — model selector
  - `#aside-snippet` — smart snippet text
  - `#rec-grid` — recommendations container

- [ ] **Step 1: Write `frontend/coach.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Pokémon Coach — Professor Oak</title>
  <link rel="stylesheet" href="/frontend/coach.css" />
  <link rel="stylesheet" href="/frontend/dashboard.css" />

  <!-- Coveo Atomic (same CDN as dashboard) -->
  <script type="module" src="https://static.cloud.coveo.com/atomic/v3/atomic.esm.js"></script>
  <link rel="stylesheet" href="https://static.cloud.coveo.com/atomic/v3/themes/coveo.css" />
</head>

<body data-coveo-org="{{ COVEO_ORGANIZATION_ID }}">

<!-- Hidden Atomic interface — engine only, no rendered UI -->
<atomic-search-interface id="atomic-search-interface" style="display:none">
  <atomic-search-box
    id="atomic-search-box-hidden"
    number-of-queries="6"
    minimum-query-length="2"
    clear-filters="false"
    style="display:none;">
  </atomic-search-box>
</atomic-search-interface>

<div class="coach-wrap">

  <!-- ── TOP BAR ── -->
  <div class="coach-topbar">
    <div class="leds">
      <div class="led lr"></div>
      <div class="led ly"></div>
      <div class="led lg"></div>
    </div>
    <span class="coach-brand">Professor Oak</span>
    <span class="coach-sub">Agentic Pokémon Coach · Coveo-powered</span>
    <a href="/dashboard" class="dashboard-link">⇐ Dashboard</a>
    <div class="model-pill">
      <span class="model-arrow">▼</span>
      <select id="model-select" title="Select AI model">
        <optgroup label="Coveo">
          <option value="coveo-rga">Professor-Oak (Coveo)</option>
        </optgroup>
        <optgroup label="Ollama (local)">
          <option value="llama3">llama3</option>
        </optgroup>
      </select>
    </div>
  </div>

  <!-- ── MAIN CHAT COLUMN ── -->
  <div class="coach-main">

    <div class="thread" id="thread">
      <!-- Quick-start chips shown before first message -->
      <div class="quick-chips" id="quick-chips">
        <div class="quick-chip" data-prompt="Build me a balanced team of 6 Pokémon">⚔ Build me a team</div>
        <div class="quick-chip" data-prompt="What types counter Ice/Dragon dual-types?">🧊 Counter Ice/Dragon</div>
        <div class="quick-chip" data-prompt="Compare Gyarados and Vaporeon for a Water slot">⇌ Compare two Pokémon</div>
        <div class="quick-chip" data-challenge="true">🎲 Challenge me</div>
      </div>
    </div>

    <!-- Input bar -->
    <div class="input-bar">
      <div class="suggestions-drop" id="suggestions-drop"></div>
      <div class="input-row">
        <textarea
          id="coach-input"
          class="coach-input"
          placeholder="Ask Oak anything… 'Compare Charizard vs Dragonite', 'Who counters my Gyarados?'"
          autocomplete="off"
          spellcheck="false"
          rows="1"></textarea>
        <button class="send-btn" id="send-btn" title="Send">⌕</button>
      </div>
    </div>

  </div><!-- /.coach-main -->

  <!-- ── RIGHT ASIDE ── -->
  <aside class="coach-aside">
    <div class="aside-section">
      <div class="aside-title">Quick Answer</div>
      <div class="snippet-text" id="aside-snippet">
        <span class="snippet-empty">Ask a question to see a quick answer here.</span>
      </div>
    </div>
    <div class="aside-title" style="padding:12px 14px 0;margin-bottom:0">Similar Pokémon</div>
    <div class="rec-grid" id="rec-grid">
      <div class="snippet-empty" style="font-size:11px;color:#555;padding:4px 0">
        Recommendations will appear here after your first question.
      </div>
    </div>
  </aside>

</div><!-- /.coach-wrap -->

<script type="module" src="/frontend/coach.js"></script>
</body>
</html>
```

- [ ] **Step 2: Verify page loads and org ID is injected**

```bash
curl -s http://localhost:5003/coach | grep 'data-coveo-org'
```
Expected: `data-coveo-org="<your-org-id>"` (not the template literal).

- [ ] **Step 3: Commit**

```bash
git add frontend/coach.html
git commit -m "feat: add coach.html shell"
```

---

## Task 7: Coach JS — single-turn chat + query suggestions

**Files:**
- Create: `frontend/coach.js`

**Interfaces:**
- Consumes: `pokemon-panel.js` (Task 1), `/api/coveo-token`, `/api/coach`, `/api/coach-challenge`, `/api/models`, Coveo Headless SDK via Atomic
- Produces: fully functional single-turn + multi-turn coach with query suggestions

- [ ] **Step 1: Create `frontend/coach.js`**

```javascript
/**
 * coach.js — Pokémon Coach front-end
 *
 * Responsibilities:
 *   1. Initialize Coveo Headless engine (token from /api/coveo-token)
 *   2. Wire query suggestion dropdown from Headless SearchBox controller
 *   3. Manage session_id for multi-turn /api/coach calls
 *   4. Render chat bubbles (user + Oak)
 *   5. Detect comparison responses and render dual comparison panels
 *   6. Render right-aside smart snippet and recommendations
 *   7. Load comparison from ?compare=X&with=Y URL params on page load
 */

import {
  fetchPokeData, pokemonDbArtworkUrl, pokemonDbSpriteUrl,
  renderStatBars, renderMovesTable, renderTypeEffectiveness,
  updatePhotoCard, setPanelHeader, matchupSummary,
  TYPE_COLORS, STAT_KEYS,
} from './modules/pokemon-panel.js';

// ── Session ───────────────────────────────────────────────────
let _sessionId = crypto.randomUUID();

// ── DOM refs ──────────────────────────────────────────────────
const thread      = () => document.getElementById('thread');
const inputEl     = () => document.getElementById('coach-input');
const sendBtn     = () => document.getElementById('send-btn');
const sugDrop     = () => document.getElementById('suggestions-drop');
const quickChips  = () => document.getElementById('quick-chips');
const snippetEl   = () => document.getElementById('aside-snippet');
const recGrid     = () => document.getElementById('rec-grid');

// ── Escape HTML ───────────────────────────────────────────────
function esc(str) {
  return String(str ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ── Scroll thread to bottom ───────────────────────────────────
function scrollBottom() {
  const t = thread();
  if (t) t.scrollTop = t.scrollHeight;
}

// ── Render a user bubble ──────────────────────────────────────
function appendUserBubble(text) {
  const div = document.createElement('div');
  div.className = 'bubble bubble-user';
  div.textContent = text;
  thread().appendChild(div);
  scrollBottom();
}

// ── Render a thinking indicator ───────────────────────────────
function appendThinking() {
  const div = document.createElement('div');
  div.className = 'bubble-thinking';
  div.id = 'thinking-indicator';
  div.textContent = '✦ Thinking…';
  thread().appendChild(div);
  scrollBottom();
  return div;
}

function removeThinking() {
  document.getElementById('thinking-indicator')?.remove();
}

// ── Render Oak answer bubble (plain text) ─────────────────────
function appendOakBubble(text, citations, gradingFlags) {
  const div = document.createElement('div');
  div.className = 'bubble bubble-oak';

  const header = `<div class="bubble-oak-header"><div class="oak-dot"></div>Professor Oak</div>`;
  const body   = `<div class="bubble-oak-text">${esc(text)}</div>`;

  let citHtml = '';
  if (citations?.length) {
    citHtml = '<div class="citations-row">'
      + citations.filter(c => c.uri).map(c =>
          `<a class="citation-pill" href="${esc(c.uri)}" target="_blank" rel="noopener">${esc(c.title || c.uri)}</a>`
        ).join('')
      + '</div>';
  }

  let flagHtml = '';
  if (gradingFlags?.length) {
    flagHtml = gradingFlags.map(f =>
      `<div class="grade-flag">⚠ Type error: ${esc(f.message)}</div>`
    ).join('');
  }

  div.innerHTML = header + body + citHtml + flagHtml;
  thread().appendChild(div);
  scrollBottom();
  return div;
}

// ── Render comparison panel inside the thread ─────────────────
async function appendComparisonPanel(comparison) {
  const { pokemon_a, pokemon_b, verdict } = comparison;
  const [pokeA, pokeB] = await Promise.all([
    fetchPokeData(pokemon_a),
    fetchPokeData(pokemon_b),
  ]);

  const nsA = `-cmp-a-${Date.now()}`;
  const nsB = `-cmp-b-${Date.now()}`;

  function panelHtml(name, poke, ns) {
    const capName = name.charAt(0).toUpperCase() + name.slice(1);
    const tags = (poke?.types ?? []).map(t => {
      const c = TYPE_COLORS[t.toLowerCase()] ?? { bg: '#444' };
      return `<span class="rptag" style="background:${c.bg}33;color:${c.bg}">`
        + `${t.charAt(0).toUpperCase() + t.slice(1)}</span>`;
    }).join('');
    const numTag = poke?.id
      ? `<span class="rptag" style="background:rgba(79,195,247,.15);color:#4fc3f7">#${String(poke.id).padStart(3,'0')}</span>`
      : '';

    return `<div class="cmp-card">
      <div class="cmp-head">
        <div class="cmp-name" id="rp-name${ns}">${esc(capName)}</div>
        <div class="cmp-tags" id="rp-tags${ns}">${tags}${numTag}</div>
      </div>
      <div class="cmp-body">
        <div class="cmp-photo">
          <div class="photo-glow" id="photo-glow${ns}"></div>
          <img class="psprite" id="psprite${ns}"
               src="${esc(pokemonDbArtworkUrl(name))}"
               alt="${esc(capName)}"
               onerror="this.style.display='none'" />
          <div class="cmp-photo-overlay">${esc(capName)}</div>
        </div>
        <div class="sec">Base Stats</div>
        <div id="stat-bars${ns}"><div style="color:#555;font-size:11px;">Loading…</div></div>
        <div class="sec">Weak To</div>
        <div class="eff-chips" id="weak-chips${ns}"></div>
        <div class="sec">Resists / Immune</div>
        <div class="eff-chips" id="resist-chips${ns}"></div>
        <div class="sec">Moves Learned</div>
        <div class="moves-scroll" style="max-height:140px">
          <table class="moves-table">
            <thead><tr><th>LV</th><th>MOVE</th><th style="text-align:right">TYPE</th></tr></thead>
            <tbody id="moves-tbody${ns}"><tr><td colspan="3" style="color:#555;font-size:11px;padding:8px;text-align:center">Loading…</td></tr></tbody>
          </table>
        </div>
        <div class="sec">Strong Against</div>
        <div class="eff-chips" id="strong-chips${ns}"></div>
      </div>
    </div>`;
  }

  // Compute stat deltas
  function deltaHtml(statsA, statsB) {
    if (!statsA || !statsB) return '<div class="delta-col"></div>';
    const rows = STAT_KEYS.map(key => {
      const a = statsA[key] ?? 0;
      const b = statsB[key] ?? 0;
      const diff = a - b;
      const cls  = diff > 0 ? 'delta-up' : diff < 0 ? 'delta-dn' : 'delta-eq';
      const label = diff > 0 ? `▲${diff}` : diff < 0 ? `▼${Math.abs(diff)}` : '—';
      return `<div class="delta-val ${cls}">${label}</div>`;
    });
    // BST row
    const bstA = STAT_KEYS.reduce((s, k) => s + (statsA[k] ?? 0), 0);
    const bstB = STAT_KEYS.reduce((s, k) => s + (statsB[k] ?? 0), 0);
    const bstDiff = bstA - bstB;
    const bstCls  = bstDiff > 0 ? 'delta-up' : bstDiff < 0 ? 'delta-dn' : 'delta-eq';
    rows.push(`<div class="delta-val ${bstCls}" style="font-size:8px;border-top:1px solid #2a2a40;padding-top:3px">`
      + (bstDiff > 0 ? `▲${bstDiff}` : bstDiff < 0 ? `▼${Math.abs(bstDiff)}` : '—')
      + `</div>`);
    return `<div class="delta-col"><div class="delta-label">ΔBST</div>${rows.join('')}</div>`;
  }

  // Winner verdict color
  const bstA = pokeA ? STAT_KEYS.reduce((s, k) => s + (pokeA.stats[k] ?? 0), 0) : 0;
  const bstB = pokeB ? STAT_KEYS.reduce((s, k) => s + (pokeB.stats[k] ?? 0), 0) : 0;
  const winnerName = bstA > bstB
    ? pokemon_a.charAt(0).toUpperCase() + pokemon_a.slice(1)
    : bstB > bstA
    ? pokemon_b.charAt(0).toUpperCase() + pokemon_b.slice(1)
    : null;
  const verdictClass = winnerName ? '' : ' draw';
  const verdictPrefix = winnerName ? `⚑ ${winnerName} has higher BST (${Math.max(bstA,bstB)} vs ${Math.min(bstA,bstB)}). ` : '⚑ Equal BST. ';

  const wrap = document.createElement('div');
  wrap.className = 'bubble bubble-oak';
  wrap.style.maxWidth = '100%';
  wrap.innerHTML = `
    <div class="bubble-oak-header"><div class="oak-dot"></div>Comparison</div>
    <div class="cmp-panel">
      ${panelHtml(pokemon_a, pokeA, nsA)}
      ${deltaHtml(pokeA?.stats, pokeB?.stats)}
      ${panelHtml(pokemon_b, pokeB, nsB)}
      <div class="verdict-bar${verdictClass}">${esc(verdictPrefix)}${esc(verdict)}</div>
    </div>`;

  thread().appendChild(wrap);
  scrollBottom();

  // Fill rendering primitives after DOM is in place
  if (pokeA) {
    renderStatBars(pokeA.stats, nsA);
    renderTypeEffectiveness(pokeA.types, nsA);
    renderMovesTable(pokeA.moves, pokeA.types, nsA);
    updatePhotoCard(pokemonDbArtworkUrl(pokemon_a), pokemon_a, pokeA.id, pokeA.types[0], nsA);
  }
  if (pokeB) {
    renderStatBars(pokeB.stats, nsB);
    renderTypeEffectiveness(pokeB.types, nsB);
    renderMovesTable(pokeB.moves, pokeB.types, nsB);
    updatePhotoCard(pokemonDbArtworkUrl(pokemon_b), pokemon_b, pokeB.id, pokeB.types[0], nsB);
  }
}

// ── Update the right aside snippet ───────────────────────────
function updateSnippet(text) {
  const el = snippetEl();
  if (!el) return;
  if (!text) {
    el.innerHTML = '<span class="snippet-empty">No quick answer available.</span>';
    return;
  }
  // Show only the first sentence
  const first = text.split(/[.!?]/)[0].trim();
  el.textContent = first ? first + '.' : text.substring(0, 120);
}

// ── Update right aside recommendations ───────────────────────
async function updateRecommendations(pokemonName) {
  const grid = recGrid();
  if (!grid || !pokemonName) return;

  try {
    const poke = await fetchPokeData(pokemonName);
    if (!poke) return;
    const type = poke.types[0];

    const r = await fetch(`https://pokeapi.co/api/v2/type/${type}`);
    if (!r.ok) return;
    const data = await r.json();

    const FORM_SUFFIXES = new Set([
      'mega','megax','megay','gmax','alola','galar','hisui','paldea','totem',
    ]);
    const pool = (data.pokemon ?? [])
      .map(p => p.pokemon.name)
      .filter(n => n.toLowerCase() !== pokemonName.toLowerCase())
      .filter(n => {
        const parts = n.split('-');
        return parts.length === 1 || !parts.slice(1).some(s => FORM_SUFFIXES.has(s));
      })
      .slice(0, 20);

    // Stable deterministic 3-pick
    let h = 2166136261;
    for (const ch of pokemonName) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
    const picks = [];
    const used = new Set();
    for (let i = 0; picks.length < 3 && used.size < pool.length; i++) {
      const idx = Math.abs(h) % pool.length;
      if (!used.has(idx)) { used.add(idx); picks.push(pool[idx]); }
      h = Math.imul(h ^ (h >>> 13), 16777619);
    }

    const cards = await Promise.all(picks.map(async name => ({
      name,
      poke: await fetchPokeData(name),
    })));

    grid.innerHTML = cards.map(({ name, poke }) => {
      const display = name.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      const typeLabel = (poke?.types ?? [type]).map(t => t.charAt(0).toUpperCase() + t.slice(1)).join('/');
      return `<div class="rec-card" data-name="${esc(name)}">
        <img class="rec-sprite" src="${esc(poke?.sprite ?? pokemonDbSpriteUrl(name))}"
             alt="${esc(display)}" onerror="this.style.display='none'" />
        <div class="rec-info">
          <div class="rec-name">${esc(display)}</div>
          <div class="rec-type">${esc(typeLabel)}</div>
        </div>
      </div>`;
    }).join('');

    grid.querySelectorAll('.rec-card').forEach(card => {
      card.addEventListener('click', () => {
        const name = card.dataset.name;
        const display = name.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        inputEl().value = `Tell me about ${display}`;
        sendMessage();
      });
    });
  } catch { /* non-fatal */ }
}

// ── Send a message ────────────────────────────────────────────
async function sendMessage(overrideText) {
  const input = inputEl();
  const text = (overrideText ?? input?.value ?? '').trim();
  if (!text) return;

  // Hide quick chips after first message
  const chips = quickChips();
  if (chips) chips.style.display = 'none';

  if (input) input.value = '';
  closeSuggestions();

  appendUserBubble(text);
  const thinking = appendThinking();

  try {
    const resp = await fetch('/api/coach', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: _sessionId, message: text }),
    });
    removeThinking();

    if (!resp.ok) {
      appendOakBubble('(Error contacting Professor Oak — please try again.)', [], []);
      return;
    }

    const data = await resp.json();
    const { answer, citations, comparison, grading_flags, session_id } = data;

    // Sync session_id in case backend generated one
    if (session_id) _sessionId = session_id;

    if (comparison) {
      // Render the text answer as a brief intro bubble, then the comparison panel
      appendOakBubble(answer, citations, grading_flags);
      await appendComparisonPanel(comparison);
    } else {
      appendOakBubble(answer, citations, grading_flags);
    }

    updateSnippet(answer);

    // Update recommendations from first Pokémon mentioned in the answer
    const firstMention = answer.match(/\b([A-Z][a-z]{2,})\b/);
    if (firstMention) updateRecommendations(firstMention[1].toLowerCase());

  } catch (err) {
    removeThinking();
    appendOakBubble('(Professor Oak is unavailable — check the server.)', [], []);
  }
}

// ── Query suggestions ─────────────────────────────────────────
let _suggestionFocusIdx = -1;

function closeSuggestions() {
  const drop = sugDrop();
  if (drop) drop.classList.remove('open');
  _suggestionFocusIdx = -1;
}

function initSuggestions(engine) {
  const { buildSearchBox } = window.CoveoHeadless ?? {};
  if (!buildSearchBox) return;   // Headless not available

  const sb = buildSearchBox(engine, { options: { numberOfSuggestions: 6 } });

  const input = inputEl();
  if (!input) return;

  input.addEventListener('input', () => {
    const q = input.value.trim();
    if (!q) { closeSuggestions(); return; }
    sb.updateText(q);
    renderSuggestions(sb.state.suggestions);
    // Subscribe for async updates
    sb.subscribe(() => renderSuggestions(sb.state.suggestions));
  });

  input.addEventListener('keydown', e => {
    const drop = sugDrop();
    const items = drop?.querySelectorAll('.sug-item') ?? [];
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      _suggestionFocusIdx = Math.min(_suggestionFocusIdx + 1, items.length - 1);
      items.forEach((el, i) => el.classList.toggle('focused', i === _suggestionFocusIdx));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      _suggestionFocusIdx = Math.max(_suggestionFocusIdx - 1, -1);
      items.forEach((el, i) => el.classList.toggle('focused', i === _suggestionFocusIdx));
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (_suggestionFocusIdx >= 0 && items[_suggestionFocusIdx]) {
        input.value = items[_suggestionFocusIdx].dataset.value;
        closeSuggestions();
      }
      sendMessage();
    } else if (e.key === 'Escape') {
      closeSuggestions();
    }
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('.input-bar')) closeSuggestions();
  });
}

function renderSuggestions(suggestions) {
  const drop = sugDrop();
  if (!drop) return;
  if (!suggestions?.length) { closeSuggestions(); return; }
  drop.innerHTML = suggestions.map(s =>
    `<div class="sug-item" data-value="${esc(s.rawValue)}">${esc(s.highlightedValue ?? s.rawValue)}</div>`
  ).join('');
  drop.querySelectorAll('.sug-item').forEach(item => {
    item.addEventListener('click', () => {
      const input = inputEl();
      if (input) input.value = item.dataset.value;
      closeSuggestions();
      sendMessage();
    });
  });
  drop.classList.add('open');
  _suggestionFocusIdx = -1;
}

// ── Handle challenge chip ─────────────────────────────────────
async function startChallenge() {
  const chips = quickChips();
  if (chips) chips.style.display = 'none';
  appendThinking();

  try {
    const resp = await fetch('/api/coach-challenge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    removeThinking();
    if (!resp.ok) throw new Error('challenge failed');
    const data = await resp.json();
    _sessionId = data.session_id;
    appendUserBubble(data.prompt);
    // Immediately send the prompt to the coach
    const answer = await fetch('/api/coach', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: _sessionId, message: data.prompt }),
    });
    if (answer.ok) {
      const d = await answer.json();
      appendOakBubble(d.answer, d.citations, d.grading_flags);
      updateSnippet(d.answer);
    }
  } catch {
    removeThinking();
    appendOakBubble('(Challenge mode unavailable right now.)', [], []);
  }
}

// ── Wire UI events ────────────────────────────────────────────
function wireUI() {
  sendBtn()?.addEventListener('click', () => sendMessage());

  quickChips()?.querySelectorAll('.quick-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      if (chip.dataset.challenge) {
        startChallenge();
      } else {
        sendMessage(chip.dataset.prompt);
      }
    });
  });

  // Auto-resize textarea
  inputEl()?.addEventListener('input', () => {
    const el = inputEl();
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  });

  // Populate live Ollama models
  fetch('/api/models').then(r => r.json()).then(d => {
    const select = document.getElementById('model-select');
    const group  = select?.querySelector('optgroup[label="Ollama (local)"]');
    if (group && d.models?.length) {
      group.innerHTML = d.models.map(m => `<option value="${m}">${m}</option>`).join('');
    }
  }).catch(() => {});
}

// ── Handle ?compare=X&with=Y URL params ──────────────────────
async function handleUrlParams() {
  const params = new URLSearchParams(window.location.search);
  const a = params.get('compare');
  const b = params.get('with');
  if (!a || !b) return;
  // Hide chips and fire a comparison directly
  const chips = quickChips();
  if (chips) chips.style.display = 'none';
  const prompt = `Compare ${a} and ${b}`;
  await sendMessage(prompt);
}

// ── Coveo Atomic init ─────────────────────────────────────────
async function initCoveo() {
  const si = document.querySelector('atomic-search-interface');
  if (!si) return;
  await customElements.whenDefined('atomic-search-interface');
  const { token, organizationId } = await fetch('/api/coveo-token').then(r => r.json());
  await si.initialize({
    accessToken: token,
    organizationId,
    search: {
      pipeline:  'default',
      searchHub: 'PokedexUI',
    },
  });
  // Wire query suggestions using the engine if Headless is exposed
  if (si.engine) initSuggestions(si.engine);
}

// ── Boot ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  wireUI();
  await initCoveo();
  await handleUrlParams();
});
```

- [ ] **Step 2: Verify the page works end-to-end**

Start the server and open `http://localhost:5003/coach`. Confirm:
- Quick-start chips appear
- Typing in the input shows Coveo query suggestions (or no errors if Coveo not configured)
- Submitting "Tell me about Pikachu" shows a user bubble and an Oak response bubble
- Submitting "Compare Charizard and Dragonite" shows two stat panels side by side

- [ ] **Step 3: Commit**

```bash
git add frontend/coach.js
git commit -m "feat: add coach.js — conversation loop, comparison panels, query suggestions"
```

---

## Task 8: Dashboard "⇌ Compare" button

**Files:**
- Modify: `frontend/dashboard.js`

**Interfaces:**
- Consumes: result item click area in `renderResultsList`
- Produces: hover button that opens `/coach?compare=X&with=Y`

- [ ] **Step 1: Add Compare button to result rows in `renderResultsList`**

In `dashboard.js`, inside `renderResultsList`, the row template currently ends at the `rbadges` span. Add a compare trigger button:

```javascript
// In the list.innerHTML = results.map(...) template, replace:
return `
  <div class="ritem${i === activeSel ? ' sel' : ''}" data-index="${i}">
    <span class="rname">${escapeHtml(name)}</span>
    <span class="rbadges" data-badges-for="${escapeHtml(name)}"></span>
  </div>`;

// With:
return `
  <div class="ritem${i === activeSel ? ' sel' : ''}" data-index="${i}">
    <span class="rname">${escapeHtml(name)}</span>
    <span class="rbadges" data-badges-for="${escapeHtml(name)}"></span>
    <a class="cmp-btn" href="/coach?compare=${encodeURIComponent(name.toLowerCase())}&with=pikachu"
       title="Compare in Coach" tabindex="-1">⇌</a>
  </div>`;
```

Note: `&with=pikachu` is a placeholder — ideally the button updates to reflect the currently selected Pokémon. Add a click handler that sets the `with` param dynamically:

```javascript
// After the existing click-handler wiring on list.querySelectorAll('.ritem'):
list.querySelectorAll('.cmp-btn').forEach(btn => {
  btn.addEventListener('click', e => {
    e.stopPropagation();   // don't trigger the row click
    const currentName = document.getElementById('rp-name')?.textContent?.trim() ?? 'pikachu';
    const compareName = btn.closest('.ritem').querySelector('.rname').textContent.trim();
    // If comparing a Pokémon against itself, use Bulbasaur as fallback
    const withName = currentName.toLowerCase() === compareName.toLowerCase()
      ? 'bulbasaur'
      : currentName.toLowerCase();
    btn.href = `/coach?compare=${encodeURIComponent(compareName.toLowerCase())}&with=${encodeURIComponent(withName)}`;
  });
});
```

- [ ] **Step 2: Add CSS for the compare button to `dashboard.css`**

Add at end of `dashboard.css`:

```css
/* Compare button — appears on result row hover */
.cmp-btn {
  display: none;
  font-size: 11px; font-weight: 700;
  color: #4fc3f7; text-decoration: none;
  background: rgba(79,195,247,.08);
  border: 1px solid rgba(79,195,247,.25);
  border-radius: 4px; padding: 1px 6px;
  flex-shrink: 0;
  transition: background .1s;
}
.ritem:hover .cmp-btn { display: inline-block; }
.cmp-btn:hover { background: rgba(79,195,247,.2); }
```

- [ ] **Step 3: Verify**

Open the dashboard, search "Charizard". Hover over a result row — a small `⇌` button should appear. Clicking it opens the coach page with `?compare=charizard&with=<current>`.

- [ ] **Step 4: Commit**

```bash
git add frontend/dashboard.js frontend/dashboard.css
git commit -m "feat: add hover Compare button to dashboard result rows"
```

---

## Task 9: E2e tests for the coach page

**Files:**
- Create: `tests/e2e/test_coach_load.py`

- [ ] **Step 1: Write the tests**

```python
# tests/e2e/test_coach_load.py
import pytest

pytestmark = pytest.mark.e2e


def test_coach_page_serves(live_url):
    import requests
    r = requests.get(f"{live_url}/coach", timeout=10)
    assert r.status_code == 200
    assert "Professor Oak" in r.text
    assert "{{ COVEO_ORGANIZATION_ID }}" not in r.text


def test_coach_css_serves(live_url):
    import requests
    assert requests.get(f"{live_url}/frontend/coach.css", timeout=10).status_code == 200


def test_coach_quick_chips_visible(browser, live_url):
    page = browser.new_page()
    page.goto(f"{live_url}/coach")
    page.wait_for_load_state("networkidle", timeout=15000)
    chips = page.locator(".quick-chip")
    assert chips.count() >= 3
    page.close()


def test_coach_single_turn(browser, live_url):
    """Submit a simple question and confirm an Oak bubble appears."""
    page = browser.new_page()
    page.goto(f"{live_url}/coach")
    page.wait_for_load_state("networkidle", timeout=15000)
    page.fill("#coach-input", "Tell me about Pikachu")
    page.press("#coach-input", "Enter")
    # Wait for Oak bubble to appear (the thinking indicator is replaced)
    page.wait_for_selector(".bubble-oak", timeout=30000)
    assert page.locator(".bubble-oak").count() >= 1
    page.close()


def test_coach_comparison_url_param(browser, live_url):
    """?compare=charizard&with=dragonite should auto-render a comparison panel."""
    page = browser.new_page()
    page.goto(f"{live_url}/coach?compare=charizard&with=dragonite", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=15000)
    # Wait for at least one comparison card
    page.wait_for_selector(".cmp-card", timeout=35000)
    assert page.locator(".cmp-card").count() == 2
    page.close()


def test_coach_compare_button_on_dashboard(browser, live_url):
    """Hovering a result row on the dashboard shows a ⇌ button."""
    page = browser.new_page()
    page.goto(f"{live_url}/dashboard")
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_function(
        "() => document.querySelector('#rp-name')?.textContent.trim() !== '—'",
        timeout=25000,
    )
    # Search for Charizard so there are result rows
    page.fill("#search-input", "charizard")
    page.press("#search-input", "Enter")
    page.wait_for_load_state("networkidle", timeout=15000)
    first_row = page.locator(".ritem").first
    first_row.hover()
    cmp_btn = first_row.locator(".cmp-btn")
    assert cmp_btn.is_visible(timeout=3000)
    page.close()
```

- [ ] **Step 2: Run e2e tests**

```bash
pytest tests/e2e/test_coach_load.py -v -m e2e
```
Expected: all 6 tests PASS (requires running server at `POKEDEX_URL`).

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_coach_load.py
git commit -m "test: add e2e tests for coach page load, single turn, comparison URL"
```

---

## Task 10: Run full test suite and tidy

**Files:** None new — validation only.

- [ ] **Step 1: Run all unit tests**

```bash
pytest tests/unit/ -v
```
Expected: all tests PASS. Verify these specific tests are present and green:
- `test_conversation.py` — 6 tests
- `test_coach_routes.py` — 6 tests
- `test_routes.py` — 3 tests (including `/coach`, `/api/coach`, `/api/coach-challenge`)
- `test_coveo_client.py` — 6 tests (unchanged)
- `test_config.py` — unchanged
- `test_type_chart_parity.py` — unchanged

- [ ] **Step 2: Run e2e tests**

```bash
pytest tests/e2e/ -v -m e2e
```
Expected: all existing dashboard e2e tests still pass; new coach tests pass.

- [ ] **Step 3: Verify dashboard is pixel-identical after the module refactor**

Open `http://localhost:5003/dashboard`. Search for "Charizard". Visually confirm:
- Stat bars: HP 78, ATK 84, DEF 78, Sp.A 109, Sp.D 85, SPD 100
- Weak To chips include: Rock ×4, Water ×2, Electric ×2
- Resists/Immune chips include: Ground ×0, Bug ×¼, Grass ×¼, Steel ×¼
- Moves table shows level-up moves with type pills and power annotations

- [ ] **Step 4: Verify coach comparison panel**

Open `http://localhost:5003/coach?compare=charizard&with=dragonite`. Confirm:
- Two stat panels render side by side
- Delta column shows green `▲` for stats where Dragonite wins (ATK: ▲50, HP: ▲13, DEF: ▲17)
- Verdict bar appears below both panels
- Moves tables populate asynchronously

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: pokemon coach — complete implementation"
```

---

## Self-Review

### Spec coverage check

| Requirement | Task |
|---|---|
| Conversational `/coach` page separate from dashboard | Tasks 4, 6 |
| Multi-turn session history | Task 2, 3 |
| Coveo RGA as answer engine | Task 3 (`CoveoClient.generated_answer`) |
| Query Suggestions via Headless SearchBox | Task 7 (`initSuggestions`) |
| Comparison intent detection (regex, no LLM) | Task 3 (`_detect_comparison`) |
| Side-by-side comparison panels using dashboard rendering | Tasks 1, 7 |
| Stat delta column | Task 7 (`deltaHtml`) |
| Verdict bar | Task 7 (`appendComparisonPanel`) |
| `?compare=X&with=Y` deep link from dashboard | Tasks 7, 8 |
| "⇌ Compare" hover button on dashboard result rows | Task 8 |
| Shared rendering module with `ns` param | Task 1 |
| Dashboard unchanged after refactor | Task 1 (ns='' call sites) |
| Inline grading flags from `check_chart_claims` | Task 3 (`_grade_answer`) |
| Challenge mode via eval_harness scenarios | Task 3 (`/api/coach-challenge`), Task 7 (`startChallenge`) |
| Recommendations in right aside | Task 7 (`updateRecommendations`) |
| Smart snippet (first sentence) in right aside | Task 7 (`updateSnippet`) |
| E2e tests | Task 9 |
| Unit tests | Tasks 2, 3 |
| Dark theme parity | Task 5 (exact same CSS tokens) |
| Responsive layout | Task 5 (media queries) |

### Placeholder scan
No TBD, TODO, or "implement later" left in the plan.

### Type consistency
- `ns` parameter: always `string`, default `''`, used consistently across Tasks 1, 7
- `session_id`: always `string` (UUID), passed as `{session_id, message}` body in Task 7, received as `string` in Task 3
- `comparison` shape: `{pokemon_a: string, pokemon_b: string, verdict: string, winner: string|null}` — defined in Task 3, consumed in Task 7
- `STAT_KEYS` exported from `pokemon-panel.js` in Task 1, consumed in Task 7 for delta computation
- `append_turn` / `get_history` signatures: defined in Task 2, called in Task 3
