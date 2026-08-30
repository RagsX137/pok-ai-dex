import { TYPE_COLORS } from '../modules/type-colors.js';

// ────────────────────────────────────────────────────────────
// 1.  Fetch Coveo credentials from Flask
//     API keys ARE the access token — no /token exchange needed.
//     The key is never in HTML source; fetched at runtime from Flask.
// ────────────────────────────────────────────────────────────
async function getCoveoCredentials() {
  const resp = await fetch('/api/coveo-token');
  return await resp.json();  // { token, organizationId }
}

// ────────────────────────────────────────────────────────────
// 2.  Initialize the atomic-search-interface element
// ────────────────────────────────────────────────────────────
async function initAtomic() {
  const searchInterface = document.querySelector('atomic-search-interface');
  if (!searchInterface) return;

  // Wait for Atomic web components to be fully defined before calling .initialize()
  // Without this, the search-box and other components are inert shells.
  await customElements.whenDefined('atomic-search-interface');

  const { token, organizationId } = await getCoveoCredentials();

  await searchInterface.initialize({
    accessToken: token,
    organizationId: organizationId,
    search: {
      pipeline:  'default',
      searchHub: 'PokedexUI',
      // The Semantic Encoder (Semantic-PokEncoder) is active via the pipeline's
      // KNN Ranking Function — no mlParameters flag needed on the client.

      // Explicitly request custom Pokémon fields — Coveo only returns a default
      // system-field subset unless these are declared here.
      fieldsToInclude: [
        'type1', 'type2',
        'hp', 'attack', 'defense', 'speed', 'total',
        'image_url', 'pokemon', 'pokedex_num',
        'generation', 'moves',
      ],
    },
  });

  // Trigger an initial search to populate results on load
  searchInterface.executeFirstSearch();

  // Append live Ollama models to the Ollama optgroup in the dropdown
  try {
    const resp   = await fetch('/api/models');
    const data   = await resp.json();
    const select = document.getElementById('model-select');
    const ollamaGroup = select?.querySelector('optgroup[label="Ollama (local)"]');
    if (ollamaGroup && data.models?.length) {
      ollamaGroup.innerHTML = data.models
        .map(m => `<option value="${m}">${m}</option>`)
        .join('');
    }
  } catch (_) { /* keep static Ollama options if Ollama is offline */ }
}

// ────────────────────────────────────────────────────────────
// 3.  Coveo result → Pokédex detail panel wiring
//     When user clicks a result, populate the bottom panel
// ────────────────────────────────────────────────────────────
// Cache PokéAPI responses to avoid redundant fetches
const _pokeCache = {};

async function fetchPokeData(name) {
  const key = name.toLowerCase();
  if (_pokeCache[key]) return _pokeCache[key];
  try {
    const r = await fetch(`https://pokeapi.co/api/v2/pokemon/${key}`);
    if (!r.ok) return null;
    const d = await r.json();
    const data = {
      sprite: d.sprites?.front_default ?? '',
      types:  d.types.map(t => t.type.name),
      stats:  Object.fromEntries(d.stats.map(s => [s.stat.name, s.base_stat])),
    };
    _pokeCache[key] = data;
    return data;
  } catch { return null; }
}

async function populateBottomPanel(result) {
  // Extract the Pokémon's plain name from the title
  // e.g. "Garchomp Pokédex: stats, moves…" → "Garchomp"
  const rawTitle = result.title ?? '';
  const pokemonName = (rawTitle.split(/\s+Pokédex/i)[0].trim()
                   || rawTitle.split(' | ')[0].trim());

  if (!pokemonName || pokemonName.toLowerCase().includes('type')) return;

  // Name label — set immediately
  const nameEl = document.querySelector('.photo-name');
  if (nameEl) nameEl.textContent = pokemonName;

  // Fetch live data from PokéAPI (Coveo raw fields are empty — Sitemap source
  // only crawls HTML, no structured metadata was indexed).
  const poke = await fetchPokeData(pokemonName);

  // Photo sprite
  const sprite = document.querySelector('.photo-sprite');
  if (sprite) {
    sprite.src = poke?.sprite
              || result.raw?.image_url
              || `/images/${pokemonName.toLowerCase()}_image.jpg`;
    sprite.style.display = '';
  }

  // Type badges in the controls row
  const types = poke?.types
             ?? [result.raw?.type1, result.raw?.type2].filter(Boolean);
  renderTypeBadges(types);

  // Stats row
  const stats = poke?.stats ?? {};
  renderStatsRow({
    hp:      stats.hp         ?? result.raw?.hp      ?? null,
    attack:  stats.attack     ?? result.raw?.attack  ?? null,
    defense: stats.defense    ?? result.raw?.defense ?? null,
    speed:   stats.speed      ?? result.raw?.speed   ?? null,
  });

  renderEvolutionChain([]);
}

function wireResultClicks() {
  document.addEventListener('atomic/result/select', (e) => {
    const result = e.detail?.result;
    if (!result) return;
    populateBottomPanel(result);
  });
}

// ────────────────────────────────────────────────────────────
// 4.  RGA — called after Coveo returns results
//     Sends top-5 snippets to /api/rga and streams answer
// ────────────────────────────────────────────────────────────
async function fetchRGAAnswer(query, results) {
  const rgaPanel = document.getElementById('rga-panel');
  if (!rgaPanel) return;
  rgaPanel.textContent = '…';
  rgaPanel.classList.add('has-answer');

  const model = document.getElementById('model-select')?.value ?? '';

  try {
    let answer;
    if (model === 'coveo-rga') {
      const resp = await fetch('/api/rga-coveo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });
      const data = await resp.json();
      answer = data.answer ?? '—';
    } else {
      const context = results.slice(0, 5).map(r => ({
        title:   r.title ?? '',
        excerpt: r.raw?.excerpt ?? r.excerpt ?? '',
      }));
      const resp = await fetch('/api/rga', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, context }),
      });
      const data = await resp.json();
      answer = data.answer ?? '—';
    }
    rgaPanel.textContent = answer;
  } catch (_) {
    rgaPanel.textContent = '(AI answer unavailable)';
  }
}

// ────────────────────────────────────────────────────────────
// 4b. Unified search bar — drives Coveo via the headless engine
// ────────────────────────────────────────────────────────────
function dispatchSearch(q) {
  // Proxy through the hidden atomic-search-box's headless SearchBox controller.
  // This is the same pattern used in test_search.py and is the only stable
  // Atomic v3 API for programmatic search without action-creator imports.
  const sb = document.querySelector('atomic-search-box');
  if (sb?.searchBox) {
    sb.searchBox.updateText(q);
    sb.searchBox.submit();
  }
}

function wireUnifiedBar() {
  const input  = document.getElementById('unified-input');
  const button = document.getElementById('unified-submit');
  if (!input) return;

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') dispatchSearch(input.value.trim());
  });
  button.addEventListener('click', () => dispatchSearch(input.value.trim()));
}

// Subscribe to the headless engine state.
// atomic/search/success is not dispatched in Atomic v3 — the only reliable
// hook is engine.subscribe(), which fires on every state change.
function wireRGA() {
  const si = document.querySelector('atomic-search-interface');
  if (!si) return;

  // Engine may not be ready synchronously; wait for it.
  const trySubscribe = () => {
    const engine = si.engine;
    if (!engine) { setTimeout(trySubscribe, 200); return; }

    let lastQuery   = null;
    let lastLoading = true; // treat initial state as loading

    engine.subscribe(() => {
      const state   = engine.state;
      const results = state?.search?.results ?? [];
      const query   = state?.query?.q ?? '';
      const loading = state?.search?.isLoading ?? false;

      // Only act when a search just *finished* loading → results ready.
      const justFinished = lastLoading === true && loading === false;
      lastLoading = loading;

      if (!justFinished || !results.length) return;

      // Auto-populate the bottom panel with the top result immediately.
      populateBottomPanel(results[0]);

      // Fire RGA only when the query text changed.
      if (query && query !== lastQuery) {
        lastQuery = query;
        fetchRGAAnswer(query, results);
      }
    });
  };

  trySubscribe();
}

// ────────────────────────────────────────────────────────────
// 5.  Type badge quick-filter buttons (control row)
// ────────────────────────────────────────────────────────────
function renderTypeBadges(types) {
  const container = document.querySelector('.ctrl-type-badges');
  if (!container) return;
  container.innerHTML = '';
  types.forEach(t => {
    const colors = TYPE_COLORS[t.toLowerCase()] ?? { bg: '#888', text: '#fff' };
    const btn = document.createElement('button');
    btn.className = 'type-badge';
    btn.textContent = t;
    btn.style.background = colors.bg;
    btn.style.color      = colors.text;
    btn.addEventListener('click', () => filterByType(t));
    container.appendChild(btn);
  });
}

function filterByType(type) {
  // Dispatch a custom event that Atomic's facet component can act on
  const facetEl = document.querySelector('atomic-facet[field="type1"]');
  if (facetEl) {
    facetEl.dispatchEvent(new CustomEvent('atomic/facet/select', {
      bubbles: true,
      detail: { facetId: 'type1', facetValue: type },
    }));
  }
}

// ────────────────────────────────────────────────────────────
// 6.  Stats row renderer (inside screen)
// ────────────────────────────────────────────────────────────
function renderStatsRow(stats) {
  const row = document.querySelector('.screen-stats-row');
  if (!row) return;
  const labels = { hp: 'HP', attack: 'Atk', defense: 'Def', speed: 'Spd' };
  row.innerHTML = Object.entries(labels)
    .map(([key, label]) => `
      <div class="stat-cell">
        <div class="stat-label">${label}</div>
        <div>${stats[key] ?? '—'}</div>
      </div>
    `).join('');
}

// ────────────────────────────────────────────────────────────
// 7.  Evolution chain renderer (bottom-right panel)
// ────────────────────────────────────────────────────────────
function renderEvolutionChain(chain) {
  const container = document.querySelector('.evo-chain');
  if (!container) return;
  if (!chain || chain.length === 0) {
    container.innerHTML = '<div class="evo-box" style="opacity:0.4;">—</div>';
    return;
  }
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
      arrow.innerHTML = `▼ <span class="evo-level">Lv.${chain[i + 1].level ?? '?'}</span>`;
      container.appendChild(arrow);
    }
  });
}

function searchPokemon(name) {
  const input = document.getElementById('unified-input');
  if (input) input.value = name;
  dispatchSearch(name);
}

// ────────────────────────────────────────────────────────────
// 8.  Facets drawer (hamburger menu toggle)
// ────────────────────────────────────────────────────────────
function wireFacetsDrawer() {
  const hamburger = document.getElementById('hamburger-btn');
  const drawer    = document.getElementById('facets-drawer');
  const close     = document.getElementById('facets-close');
  hamburger?.addEventListener('click', () => drawer?.classList.toggle('open'));
  close?.addEventListener('click',     () => drawer?.classList.remove('open'));
}

// ────────────────────────────────────────────────────────────
// 9.  Model selector — updates OLLAMA_MODEL via Flask
// ────────────────────────────────────────────────────────────
function wireModelSelector() {
  document.getElementById('model-select')?.addEventListener('change', async (e) => {
    try {
      await fetch('/api/set-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: e.target.value }),
      });
    } catch (_) { /* non-fatal */ }
  });
}

// ────────────────────────────────────────────────────────────
// 10. Power button — reset screen to default state
// ────────────────────────────────────────────────────────────
function wirePowerButton() {
  document.getElementById('power-btn')?.addEventListener('click', () => {
    const input = document.getElementById('unified-input');
    if (input) input.value = '';

    const si = document.querySelector('atomic-search-interface');
    if (si) si.executeFirstSearch();

    const sprite = document.querySelector('.photo-sprite');
    if (sprite) sprite.src = '/images/placeholder.png';

    const nameEl = document.querySelector('.photo-name');
    if (nameEl) nameEl.textContent = 'Pokémon';

    const rgaPanel = document.getElementById('rga-panel');
    if (rgaPanel) { rgaPanel.textContent = ''; rgaPanel.classList.remove('has-answer'); }

    const evoChain = document.querySelector('.evo-chain');
    if (evoChain) evoChain.innerHTML = '<div class="evo-box" style="opacity:0.4;">—</div>';

    renderTypeBadges(['Grass', 'Water']);
  });
}

// ────────────────────────────────────────────────────────────
// 11. Boot
// ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await initAtomic();
  wireResultClicks();
  wireUnifiedBar();
  wireRGA();
  wireFacetsDrawer();
  wireModelSelector();
  wirePowerButton();
  renderTypeBadges(['Grass', 'Water']);  // default type badge display on load
});
