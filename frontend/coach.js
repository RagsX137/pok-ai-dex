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
  updatePhotoCard,
  TYPE_COLORS, STAT_KEYS,
} from './modules/pokemon-panel.js';

// ── Session ───────────────────────────────────────────────────
let _sessionId = crypto.randomUUID();

// ── In-flight guard ──────────────────────────────────────────
let _busy = false;

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

// ── Render error bubble ───────────────────────────────────────
function appendErrorBubble(text) {
  const div = document.createElement('div');
  div.className = 'bubble bubble-error';
  div.textContent = text;
  thread().appendChild(div);
  thread().scrollTop = thread().scrollHeight;
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

  const nsA = `-cmp-a-${crypto.randomUUID()}`;
  const nsB = `-cmp-b-${crypto.randomUUID()}`;

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
          <img class="psprite cmp-artwork" id="psprite${ns}"
               src="${esc(pokemonDbArtworkUrl(name))}"
               alt="${esc(capName)}" />
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

  // Wire image error handlers (CSP-safe — no inline onerror attributes)
  wrap.querySelectorAll('img.cmp-artwork').forEach(img => {
    img.addEventListener('error', () => { img.style.display = 'none'; });
  });

  // Fill rendering primitives after DOM is in place
  if (pokeA) {
    renderStatBars(pokeA.stats, nsA);
    renderTypeEffectiveness(pokeA.types, nsA);
    renderMovesTable(pokeA.moves, pokeA.types, nsA);
    updatePhotoCard(pokemonDbArtworkUrl(pokemon_a), pokemon_a, pokeA.id, pokeA.types[0], nsA);
  } else {
    const cardA = wrap.querySelector(`#rp-name${nsA}`)?.closest('.cmp-card');
    if (cardA) cardA.innerHTML = `<p style="color:#e57373;padding:8px 0">Pokémon not found: ${esc(pokemon_a)}</p>`;
  }
  if (pokeB) {
    renderStatBars(pokeB.stats, nsB);
    renderTypeEffectiveness(pokeB.types, nsB);
    renderMovesTable(pokeB.moves, pokeB.types, nsB);
    updatePhotoCard(pokemonDbArtworkUrl(pokemon_b), pokemon_b, pokeB.id, pokeB.types[0], nsB);
  } else {
    const cardB = wrap.querySelector(`#rp-name${nsB}`)?.closest('.cmp-card');
    if (cardB) cardB.innerHTML = `<p style="color:#e57373;padding:8px 0">Pokémon not found: ${esc(pokemon_b)}</p>`;
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
             alt="${esc(display)}" />
        <div class="rec-info">
          <div class="rec-name">${esc(display)}</div>
          <div class="rec-type">${esc(typeLabel)}</div>
        </div>
      </div>`;
    }).join('');

    // Wire image error handlers (CSP-safe)
    grid.querySelectorAll('img.rec-sprite').forEach(img => {
      img.addEventListener('error', () => { img.style.display = 'none'; });
    });
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
  if (_busy) return;
  const input = inputEl();
  const text = (overrideText ?? input?.value ?? '').trim();
  if (!text) return;

  _busy = true;
  sendBtn().disabled = true;

  try {
    // Hide quick chips after first message
    const chips = quickChips();
    if (chips) chips.style.display = 'none';

    if (input) input.value = '';
    closeSuggestions();

    appendUserBubble(text);
    appendThinking();

    try {
      const resp = await fetch('/api/coach', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: _sessionId, message: text }),
      });
      removeThinking();

      if (!resp.ok) {
        appendErrorBubble('(Error contacting Professor Oak — please try again.)');
        return;
      }

      const data = await resp.json();
      const { answer, citations, comparison, grading_flags } = data;

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
      appendErrorBubble('(Professor Oak is unavailable — check the server.)');
    }
  } finally {
    _busy = false;
    sendBtn().disabled = false;
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
  // Subscribe once — outside the event handler to avoid accumulation
  sb.subscribe(() => renderSuggestions(sb.state.suggestions));

  const input = inputEl();
  if (!input) return;

  input.addEventListener('input', () => {
    const q = input.value.trim();
    if (!q) { closeSuggestions(); return; }
    sb.updateText(q);
    renderSuggestions(sb.state.suggestions);
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
    appendErrorBubble('(Challenge mode unavailable right now.)');
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
