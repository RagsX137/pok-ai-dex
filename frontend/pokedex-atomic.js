import { TYPE_COLORS } from './type-colors.js';

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
function wireResultClicks() {
  document.addEventListener('atomic/result/select', (e) => {
    const result = e.detail?.result;
    if (!result) return;

    // Title format examples:
    //   "Garchomp Pokédex: stats, moves, evolution & locations | Pokémon Database"
    //   "Dragon type Pokémon | Pokémon Database"
    const rawTitle = result.title ?? '';
    const pokemonName = rawTitle.split(/\s+Pokédex/i)[0].trim()
                     || rawTitle.split(' | ')[0].trim();

    // Show the name from the Coveo result title
    const nameEl = document.querySelector('.photo-name');
    if (nameEl) nameEl.textContent = pokemonName;

    // Use Coveo raw fields for type badges and stats if available
    const type1 = result.raw?.type1 ?? '';
    const type2 = result.raw?.type2 ?? '';
    renderTypeBadges([type1, type2].filter(Boolean));

    renderStatsRow({
      hp:      result.raw?.hp      ?? null,
      attack:  result.raw?.attack  ?? null,
      defense: result.raw?.defense ?? null,
      speed:   result.raw?.speed   ?? null,
    });

    renderEvolutionChain([]);
  });
}

// ────────────────────────────────────────────────────────────
// 4.  RGA — called after Coveo returns results
//     Sends top-5 snippets to /api/rga and streams answer
// ────────────────────────────────────────────────────────────
async function fetchRGAAnswer(query, results) {
  const rgaPanel = document.querySelector('.rga-panel');
  if (!rgaPanel) return;
  rgaPanel.textContent = '…';

  const model = document.getElementById('model-select')?.value ?? '';

  try {
    let answer;
    if (model === 'coveo-rga') {
      // ── Coveo Relevance Generative Answering (Professor-Oak) ──────────────
      // Sends just the query — Coveo retrieves passages and generates the answer
      // server-side using the model associated with the pipeline.
      const resp = await fetch('/api/rga-coveo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });
      const data = await resp.json();
      answer = data.answer ?? '—';
    } else {
      // ── Ollama (local LLM) ────────────────────────────────────────────────
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

// Wire to Atomic's search success event
function wireRGA() {
  document.addEventListener('atomic/search/success', (e) => {
    const query   = document.querySelector('atomic-search-box')
                      ?.shadowRoot?.querySelector('input')?.value ?? '';
    const results = e.detail?.results ?? [];
    if (query && results.length) fetchRGAAnswer(query, results);
  });
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
  const searchInterface = document.querySelector('atomic-search-interface');
  const searchBox = document.querySelector('atomic-search-box');
  if (searchBox) searchBox.setAttribute('value', name);
  if (searchInterface) searchInterface.executeFirstSearch();
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
    const si = document.querySelector('atomic-search-interface');
    if (si) si.executeFirstSearch();

    const sprite = document.querySelector('.photo-sprite');
    if (sprite) sprite.src = '/images/placeholder.png';

    const nameEl = document.querySelector('.photo-name');
    if (nameEl) nameEl.textContent = 'Pokémon';

    const rgaPanel = document.querySelector('.rga-panel');
    if (rgaPanel) rgaPanel.textContent = 'Ask me anything about Pokémon…';

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
  wireRGA();
  wireFacetsDrawer();
  wireModelSelector();
  wirePowerButton();
  renderTypeBadges(['Grass', 'Water']);  // default type badge display on load
});
