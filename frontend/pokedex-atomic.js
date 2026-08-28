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
  return data.token;  // Coveo search token scoped to this user
}

// ────────────────────────────────────────────────────────────
// 2.  Initialize the atomic-search-interface element
// ────────────────────────────────────────────────────────────
async function initAtomic() {
  const searchInterface = document.querySelector('atomic-search-interface');
  if (!searchInterface) return;

  const token = await getSearchToken();
  const orgId = document.body.dataset.coveoOrg;  // injected via data attr in HTML

  await searchInterface.initialize({
    accessToken: token,
    organizationId: orgId,
    search: {
      pipeline:  'PokedexPipeline',
      searchHub: 'PokedexUI',
    },
  });

  // Trigger an initial search to populate results on load
  searchInterface.executeFirstSearch();

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
    const sprite = document.querySelector('.photo-sprite');
    if (sprite) sprite.src = imageUrl;
    const nameEl = document.querySelector('.photo-name');
    if (nameEl) nameEl.textContent = name;

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
  if (!rgaPanel) return;
  rgaPanel.textContent = '…';

  try {
    const resp = await fetch('/api/rga', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, context }),
    });
    const data = await resp.json();
    rgaPanel.textContent = data.answer ?? '—';
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
