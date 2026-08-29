/**
 * Pokédex V2B — Dark Dashboard
 * Drives the 3-column layout:
 *   - Left sidebar:  type chips + generation list → Coveo facet filters
 *   - Center:        search bar → Coveo results → photo card → similar Pokémon
 *   - Right panel:   stats · moves · type effectiveness · RGA recommendation
 */

import { TYPE_COLORS } from './type-colors.js';

// ─────────────────────────────────────────────────────────────
// TYPE EFFECTIVENESS DATA  (simplified chart, Gen I–IX standard)
// ─────────────────────────────────────────────────────────────
const TYPE_CHART = {
  fire:     { weak: ['water','rock','ground'],       strong: ['grass','bug','steel','ice','fairy'] },
  water:    { weak: ['electric','grass'],             strong: ['fire','rock','ground'] },
  grass:    { weak: ['fire','ice','poison','flying','bug'], strong: ['water','rock','ground'] },
  electric: { weak: ['ground'],                       strong: ['water','flying'] },
  psychic:  { weak: ['bug','ghost','dark'],           strong: ['fighting','poison'] },
  ice:      { weak: ['fire','fighting','rock','steel'], strong: ['grass','ground','flying','dragon'] },
  dragon:   { weak: ['ice','dragon','fairy'],         strong: ['dragon'] },
  dark:     { weak: ['fighting','bug','fairy'],       strong: ['psychic','ghost'] },
  fairy:    { weak: ['poison','steel'],               strong: ['fighting','dragon','dark'] },
  fighting: { weak: ['psychic','flying','fairy'],     strong: ['normal','ice','rock','dark','steel'] },
  poison:   { weak: ['ground','psychic'],             strong: ['grass','fairy'] },
  ground:   { weak: ['water','grass','ice'],          strong: ['fire','electric','poison','rock','steel'] },
  flying:   { weak: ['electric','ice','rock'],        strong: ['grass','fighting','bug'] },
  ghost:    { weak: ['ghost','dark'],                 strong: ['psychic','ghost'] },
  rock:     { weak: ['water','grass','fighting','ground','steel'], strong: ['fire','ice','flying','bug'] },
  bug:      { weak: ['fire','flying','rock'],         strong: ['grass','psychic','dark'] },
  steel:    { weak: ['fire','fighting','ground'],     strong: ['ice','rock','fairy'] },
  normal:   { weak: ['fighting'],                     strong: [] },
};

// Generation → Roman numeral mapping (used for Coveo facet values)
const GEN_MAP = {
  I: 'gen-i', II: 'gen-ii', III: 'gen-iii', IV: 'gen-iv',
  V: 'gen-v', VI: 'gen-vi', VII: 'gen-vii', VIII: 'gen-viii', IX: 'gen-ix',
};

// ─────────────────────────────────────────────────────────────
// PokéAPI cache
// ─────────────────────────────────────────────────────────────
const _cache = {};

async function fetchPokeData(name) {
  const key = name.toLowerCase().trim();
  if (_cache[key]) return _cache[key];
  try {
    const r = await fetch(`https://pokeapi.co/api/v2/pokemon/${key}`);
    if (!r.ok) return null;
    const d = await r.json();

    // Moves: level-up only, sorted by level
    const levelMoves = d.moves
      .flatMap(m => m.version_group_details
        .filter(v => v.move_learn_method.name === 'level-up')
        .map(v => ({ name: m.move.name, level: v.level_learned_at }))
      )
      .sort((a, b) => a.level - b.level)
      // Deduplicate (same move appears across version groups)
      .filter((m, i, arr) => arr.findIndex(x => x.name === m.name) === i);

    const data = {
      id:       d.id,
      sprite:   d.sprites?.front_default ?? '',
      types:    d.types.map(t => t.type.name),
      stats:    Object.fromEntries(d.stats.map(s => [s.stat.name, s.base_stat])),
      moves:    levelMoves,
    };
    _cache[key] = data;
    return data;
  } catch {
    return null;
  }
}

// ─────────────────────────────────────────────────────────────
// 1. Build type chips in the left sidebar
// ─────────────────────────────────────────────────────────────
function buildTypeGrid() {
  const grid = document.getElementById('type-grid');
  if (!grid) return;

  Object.entries(TYPE_COLORS).forEach(([type, colors]) => {
    const chip = document.createElement('div');
    chip.className = 'tchip';
    chip.dataset.type = type;
    chip.textContent = type.charAt(0).toUpperCase() + type.slice(1);
    chip.style.background = colors.bg;
    chip.style.color = colors.text;
    chip.addEventListener('click', () => toggleTypeFilter(chip, type));
    grid.appendChild(chip);
  });
}

function toggleTypeFilter(chip, type) {
  const wasOn = chip.classList.toggle('on');
  // Drive Coveo facet via the engine
  const si = document.querySelector('atomic-search-interface');
  const engine = si?.engine;
  if (!engine) return;

  const state = engine.state;
  // Use headless facet — find the facet for type1
  // Simplest reliable approach: submit a new search with aq override
  const currentAq = (state?.query?.aq ?? '');
  const typeExpr = `@type1=="${type}" OR @type2=="${type}"`;

  if (wasOn) {
    const allOn = [...document.querySelectorAll('.tchip.on')]
      .map(c => `(@type1=="${c.dataset.type}" OR @type2=="${c.dataset.type}")`);
    updateAdvancedQuery(allOn.length ? allOn.join(' OR ') : '');
  } else {
    const allOn = [...document.querySelectorAll('.tchip.on')]
      .map(c => `(@type1=="${c.dataset.type}" OR @type2=="${c.dataset.type}")`);
    updateAdvancedQuery(allOn.length ? allOn.join(' OR ') : '');
  }
}

function updateAdvancedQuery(aq) {
  const sb = document.querySelector('atomic-search-box');
  if (!sb?.searchBox) return;
  // Resubmit current query; AQ is set via engine action
  const si = document.querySelector('atomic-search-interface');
  const engine = si?.engine;
  if (!engine) return;

  // Coveo headless: dispatch setAdvancedSearchQuery then executeSearch
  try {
    const { buildSearchParameterSerializer } = window.CoveoHeadless ?? {};
    // Fallback: use the query field from state
    const q = engine.state?.query?.q ?? '';
    engine.dispatch(
      engine.actions?.query?.updateAdvancedSearchQueries?.({ aq }) ??
      { type: 'query/updateAdvancedSearchQueries', payload: { aq } }
    );
    engine.dispatch({ type: 'search/executeSearch', payload: {} });
  } catch (_) {
    // If headless actions are unavailable, just resubmit the current text
    const q = engine.state?.query?.q ?? '';
    dispatchSearch(q || '*');
  }
}

// ─────────────────────────────────────────────────────────────
// 2. Generation list wiring
// ─────────────────────────────────────────────────────────────
function wireGenList() {
  document.querySelectorAll('.gen-item').forEach(item => {
    item.addEventListener('click', () => {
      document.querySelectorAll('.gen-item').forEach(i => i.classList.remove('on'));
      item.classList.add('on');
      const gen = GEN_MAP[item.dataset.gen] ?? '';
      // Dispatch a generation-filtered search
      if (gen) dispatchSearch(`generation:${gen}`);
    });
  });
}

// ─────────────────────────────────────────────────────────────
// 3. Map card — gen toggle buttons (UI only, updates map pills)
// ─────────────────────────────────────────────────────────────
function wireMapToggles() {
  document.querySelectorAll('.gtbtn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.gtbtn').forEach(b => b.classList.remove('on'));
      btn.classList.add('on');
    });
  });
}

function updateMapCard(locationAreas) {
  const pills = document.getElementById('map-pills');
  if (!pills) return;
  if (!locationAreas || locationAreas.length === 0) {
    pills.innerHTML = '<span class="mpill">Unknown</span>';
    return;
  }
  pills.innerHTML = locationAreas.slice(0, 4).map(loc => {
    const name = loc.location_area?.name ?? loc.name ?? '?';
    const label = name.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    return `<span class="mpill">${label}</span>`;
  }).join('');
}

async function fetchLocationAreas(pokemonId) {
  try {
    const r = await fetch(`https://pokeapi.co/api/v2/pokemon/${pokemonId}/encounters`);
    if (!r.ok) return [];
    return await r.json();
  } catch { return []; }
}

// ─────────────────────────────────────────────────────────────
// 4. Coveo Atomic initialisation
// ─────────────────────────────────────────────────────────────
async function initAtomic() {
  const si = document.querySelector('atomic-search-interface');
  if (!si) return;

  await customElements.whenDefined('atomic-search-interface');

  const resp = await fetch('/api/coveo-token');
  const { token, organizationId } = await resp.json();

  await si.initialize({
    accessToken: token,
    organizationId,
    search: {
      pipeline:  'default',
      searchHub: 'PokedexUI',
      fieldsToInclude: [
        'type1', 'type2',
        'hp', 'attack', 'defense', 'speed', 'total',
        'image_url', 'pokemon', 'pokedex_num',
        'generation', 'moves',
      ],
    },
  });

  si.executeFirstSearch();

  // Populate live Ollama models
  try {
    const mResp = await fetch('/api/models');
    const mData = await mResp.json();
    const select = document.getElementById('model-select');
    const group  = select?.querySelector('optgroup[label="Ollama (local)"]');
    if (group && mData.models?.length) {
      group.innerHTML = mData.models.map(m => `<option value="${m}">${m}</option>`).join('');
    }
  } catch (_) { /* keep static options */ }
}

// ─────────────────────────────────────────────────────────────
// 5. Search dispatch helper (drives the hidden Atomic SearchBox)
// ─────────────────────────────────────────────────────────────
function dispatchSearch(q) {
  const sb = document.querySelector('atomic-search-box');
  if (sb?.searchBox) {
    sb.searchBox.updateText(q);
    sb.searchBox.submit();
  }
}

// ─────────────────────────────────────────────────────────────
// 6. Search bar wiring
// ─────────────────────────────────────────────────────────────
function wireSearchBar() {
  const input = document.getElementById('search-input');
  const btn   = document.getElementById('search-btn');
  if (!input) return;

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') dispatchSearch(input.value.trim());
  });
  btn?.addEventListener('click', () => dispatchSearch(input.value.trim()));
}

// ─────────────────────────────────────────────────────────────
// 7. Subscribe to Coveo engine state → render results list
// ─────────────────────────────────────────────────────────────
function wireEngineSubscription() {
  const si = document.querySelector('atomic-search-interface');
  if (!si) return;

  let lastLoading = true;
  let lastQuery   = null;

  const trySubscribe = () => {
    const engine = si.engine;
    if (!engine) { setTimeout(trySubscribe, 200); return; }

    engine.subscribe(() => {
      const state   = engine.state;
      const results = state?.search?.results ?? [];
      const query   = state?.query?.q ?? '';
      const loading = state?.search?.isLoading ?? false;
      const total   = state?.search?.response?.totalCountFiltered ?? results.length;

      const justFinished = lastLoading === true && loading === false;
      lastLoading = loading;

      if (!justFinished) return;

      // Render results list
      renderResultsList(results, total);

      // Auto-select the top result
      if (results.length > 0) {
        selectResult(results[0], true);
      }

      // Fire RGA when query changed
      if (query && query !== lastQuery) {
        lastQuery = query;
        const q = document.getElementById('search-input');
        if (q && !q.value) q.value = query;
        fetchRGA(query, results);
      }
    });
  };

  trySubscribe();
}

// ─────────────────────────────────────────────────────────────
// 8. Render the results list in the center column
// ─────────────────────────────────────────────────────────────
function renderResultsList(results, total) {
  const list  = document.getElementById('results-list');
  const count = document.getElementById('result-count');
  if (!list) return;

  count.textContent = total ? `${total} found` : '—';

  if (!results.length) {
    list.innerHTML = '<div class="ritem" style="color:#555;font-size:11px;padding:10px 12px;">No results found</div>';
    return;
  }

  list.innerHTML = results.map((r, i) => {
    const name  = extractPokemonName(r.title);
    const type1 = r.raw?.type1 ?? '';
    const type2 = r.raw?.type2 ?? '';
    return `
      <div class="ritem${i === 0 ? ' sel' : ''}" data-index="${i}">
        <span class="rname">${name}</span>
        ${typeBadgeHtml(type1)}
        ${type2 ? typeBadgeHtml(type2) : ''}
      </div>`;
  }).join('');

  // Wire click handlers
  list.querySelectorAll('.ritem').forEach(item => {
    item.addEventListener('click', () => {
      list.querySelectorAll('.ritem').forEach(i => i.classList.remove('sel'));
      item.classList.add('sel');
      const idx = parseInt(item.dataset.index, 10);
      selectResult(results[idx], false);
    });
  });
}

function typeBadgeHtml(type) {
  if (!type) return '';
  const t = type.toLowerCase();
  const colors = TYPE_COLORS[t] ?? { bg: '#444', text: '#ccc' };
  return `<span class="rbadge" style="background:${colors.bg}22;color:${colors.bg};border:1px solid ${colors.bg}44">${type}</span>`;
}

function extractPokemonName(title) {
  // "Charizard Pokédex: stats, moves…" → "Charizard"
  return (title?.split(/\s+Pokédex/i)[0].trim()
       || title?.split(' | ')[0].trim()
       || title
       || '?');
}

// ─────────────────────────────────────────────────────────────
// 9. Select a result → populate photo, right panel, similar
// ─────────────────────────────────────────────────────────────
async function selectResult(result, autoSelect) {
  const name = extractPokemonName(result.title);
  if (!name || name.length < 2) return;

  // Immediately update name labels
  setPhotoName(name, null);
  setRightPanelName(name, [], null);

  const poke = await fetchPokeData(name);
  if (!poke) return;

  // Photo card
  setPhotoName(name, poke.id);
  updatePhotoCard(poke.sprite, name, poke.id, poke.types[0]);

  // Right panel
  setRightPanelName(name, poke.types, poke.id);
  renderStatBars(poke.stats);
  renderMovesTable(poke.moves, poke.types);
  renderTypeEffectiveness(poke.types);

  // Map location
  const locations = await fetchLocationAreas(poke.id);
  updateMapCard(locations);

  // Similar Pokémon (same primary type)
  renderSimilarPokemon(poke.types[0], name);
}

// ─────────────────────────────────────────────────────────────
// 10. Photo card updater
// ─────────────────────────────────────────────────────────────
function updatePhotoCard(spriteUrl, name, pokeId, primaryType) {
  const img = document.getElementById('psprite');
  if (img) {
    img.src = spriteUrl || `/images/${name.toLowerCase()}_image.jpg`;
    img.style.display = '';
  }

  // Tint the glow to the primary type colour
  const glow = document.getElementById('photo-glow');
  if (glow && primaryType) {
    const colors = TYPE_COLORS[primaryType.toLowerCase()] ?? {};
    const hex = colors.bg ?? '#ff9832';
    glow.style.background = `radial-gradient(ellipse at 50% 60%, ${hex}22 0%, transparent 70%)`;
  }
}

function setPhotoName(name, pokeId) {
  const nameEl = document.getElementById('photo-name');
  const numEl  = document.getElementById('photo-num');
  if (nameEl) nameEl.textContent = name;
  if (numEl && pokeId)  numEl.textContent = `#${String(pokeId).padStart(3, '0')}`;
  else if (numEl) numEl.textContent = '';
}

// ─────────────────────────────────────────────────────────────
// 11. Right panel — name + type tags
// ─────────────────────────────────────────────────────────────
function setRightPanelName(name, types, pokeId) {
  const nameEl = document.getElementById('rp-name');
  const tagsEl = document.getElementById('rp-tags');
  if (nameEl) nameEl.textContent = name;
  if (tagsEl && types.length) {
    tagsEl.innerHTML = types.map(t => {
      const colors = TYPE_COLORS[t.toLowerCase()] ?? { bg: '#444', text: '#ccc' };
      return `<span class="rptag" style="background:${colors.bg}33;color:${colors.bg}">${t.charAt(0).toUpperCase() + t.slice(1)}</span>`;
    }).join('') + (pokeId ? `<span class="rptag" style="background:rgba(79,195,247,.15);color:#4fc3f7">#${String(pokeId).padStart(3,'0')}</span>` : '');
  }
}

// ─────────────────────────────────────────────────────────────
// 12. Stat bars
// ─────────────────────────────────────────────────────────────
const STAT_CONFIG = [
  { key: 'hp',              label: 'HP',  color: '#44dd44' },
  { key: 'attack',          label: 'ATK', color: '#f0d040' },
  { key: 'defense',         label: 'DEF', color: '#4fc3f7' },
  { key: 'special-attack',  label: 'Sp.A',color: '#ff6b81' },
  { key: 'special-defense', label: 'Sp.D',color: '#ab6ac8' },
  { key: 'speed',           label: 'SPD', color: '#ff9c54' },
];
const STAT_MAX = 255;

function renderStatBars(stats) {
  const container = document.getElementById('stat-bars');
  if (!container) return;
  container.innerHTML = STAT_CONFIG.map(({ key, label, color }) => {
    const val = stats[key] ?? 0;
    const pct = Math.round((val / STAT_MAX) * 100);
    return `
      <div class="srow2">
        <span class="slbl">${label}</span>
        <div class="strk"><div class="sfil" style="width:${pct}%;background:${color}"></div></div>
        <span class="sval">${val}</span>
      </div>`;
  }).join('');
}

// ─────────────────────────────────────────────────────────────
// 13. Moves table
// ─────────────────────────────────────────────────────────────
async function renderMovesTable(moves, pokeTypes) {
  const tbody = document.getElementById('moves-tbody');
  if (!tbody) return;

  if (!moves || !moves.length) {
    tbody.innerHTML = '<tr><td colspan="3" style="color:#555;font-size:11px;text-align:center;padding:10px;">No move data</td></tr>';
    return;
  }

  // For each move we need its type — batch-fetch from PokéAPI
  // Show up to 20 moves; fetch types lazily
  const displayed = moves.slice(0, 20);

  // Render immediately with placeholders
  tbody.innerHTML = displayed.map(m => {
    const lvLabel = m.level === 0 ? '—' : m.level;
    const moveName = m.name.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    return `<tr data-move="${m.name}">
      <td class="mlv">${lvLabel}</td>
      <td class="mname">${moveName}</td>
      <td class="mtype-cell"><span class="mtype-pill" style="background:#2a2a3e;color:#888">…</span></td>
    </tr>`;
  }).join('');

  // Fetch move types in the background
  for (const m of displayed) {
    fetchMoveType(m.name).then(type => {
      const row = tbody.querySelector(`tr[data-move="${m.name}"]`);
      if (!row) return;
      const cell = row.querySelector('.mtype-pill');
      if (!cell) return;
      const t = (type ?? 'normal').toLowerCase();
      const colors = TYPE_COLORS[t] ?? { bg: '#9099A1', text: '#fff' };
      cell.style.background = colors.bg + '33';
      cell.style.color = colors.bg;
      cell.textContent = t.charAt(0).toUpperCase() + t.slice(1);
    });
  }
}

const _moveCache = {};
async function fetchMoveType(moveName) {
  if (_moveCache[moveName]) return _moveCache[moveName];
  try {
    const r = await fetch(`https://pokeapi.co/api/v2/move/${moveName}`);
    if (!r.ok) return 'normal';
    const d = await r.json();
    const type = d.type?.name ?? 'normal';
    _moveCache[moveName] = type;
    return type;
  } catch { return 'normal'; }
}

// ─────────────────────────────────────────────────────────────
// 14. Type effectiveness
// ─────────────────────────────────────────────────────────────
function renderTypeEffectiveness(types) {
  const weakEl   = document.getElementById('weak-chips');
  const strongEl = document.getElementById('strong-chips');
  if (!weakEl || !strongEl) return;

  // Combine weak/strong for all types
  const weakSet   = new Set();
  const strongSet = new Set();

  types.forEach(t => {
    const t2 = t.toLowerCase();
    const chart = TYPE_CHART[t2];
    if (!chart) return;
    chart.weak.forEach(w => weakSet.add(w));
    chart.strong.forEach(s => strongSet.add(s));
  });

  // ×4 indicator for dual-type double weaknesses
  const weakCounts = {};
  types.forEach(t => {
    (TYPE_CHART[t.toLowerCase()]?.weak ?? []).forEach(w => {
      weakCounts[w] = (weakCounts[w] ?? 0) + 1;
    });
  });

  weakEl.innerHTML = [...weakSet].map(w => {
    const label = w.charAt(0).toUpperCase() + w.slice(1);
    const mult = weakCounts[w] >= 2 ? ' ×4' : ' ×2';
    return `<span class="echip wk">${label}${mult}</span>`;
  }).join('') || '<span style="color:#555;font-size:11px;">None</span>';

  strongEl.innerHTML = [...strongSet].map(s => {
    const label = s.charAt(0).toUpperCase() + s.slice(1);
    return `<span class="echip st">${label}</span>`;
  }).join('') || '<span style="color:#555;font-size:11px;">None</span>';
}

// ─────────────────────────────────────────────────────────────
// 15. Similar Pokémon — fetch 3 same-type Pokémon from PokéAPI
// ─────────────────────────────────────────────────────────────
async function renderSimilarPokemon(primaryType, excludeName) {
  const grid = document.getElementById('similar-grid');
  if (!grid) return;

  grid.innerHTML = '<div class="sim-placeholder">Loading…</div>';

  try {
    const t   = primaryType.toLowerCase();
    const r   = await fetch(`https://pokeapi.co/api/v2/type/${t}`);
    if (!r.ok) { grid.innerHTML = '<div class="sim-placeholder">—</div>'; return; }
    const data = await r.json();

    // Pick 3 random Pokémon of this type (excluding the current one)
    const pool = (data.pokemon ?? [])
      .map(p => p.pokemon.name)
      .filter(n => n.toLowerCase() !== excludeName.toLowerCase())
      .filter(n => !n.includes('-mega') && !n.includes('-gmax'));  // filter forms

    const picked = shuffleSlice(pool, 3);
    if (!picked.length) {
      grid.innerHTML = '<div class="sim-placeholder">No similar Pokémon found</div>';
      return;
    }

    // Fetch sprites
    const cards = await Promise.all(picked.map(async name => {
      const poke = await fetchPokeData(name);
      return { name, poke };
    }));

    grid.innerHTML = cards.map(({ name, poke }) => {
      const displayName = name.charAt(0).toUpperCase() + name.slice(1);
      const t2 = primaryType.toLowerCase();
      const colors = TYPE_COLORS[t2] ?? { bg: '#444', text: '#ccc' };
      return `
        <div class="sim-card" data-name="${name}">
          <img class="sim-sprite"
               src="${poke?.sprite ?? ''}"
               alt="${displayName}"
               onerror="this.style.display='none'" />
          <div class="sim-name">${displayName}</div>
          <span class="sim-type" style="background:${colors.bg}33;color:${colors.bg};border:1px solid ${colors.bg}66">
            ${primaryType.charAt(0).toUpperCase() + primaryType.slice(1)}
          </span>
        </div>`;
    }).join('');

    // Wire clicks on similar cards
    grid.querySelectorAll('.sim-card').forEach(card => {
      card.addEventListener('click', () => {
        grid.querySelectorAll('.sim-card').forEach(c => c.classList.remove('sel'));
        card.classList.add('sel');
        const name = card.dataset.name;
        document.getElementById('search-input').value = name;
        dispatchSearch(name);
      });
    });
  } catch {
    grid.innerHTML = '<div class="sim-placeholder">—</div>';
  }
}

function shuffleSlice(arr, n) {
  const copy = [...arr];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, n);
}

// ─────────────────────────────────────────────────────────────
// 16. RGA — generative answer → fills ai-answer (center) and
//     ai-rec-txt (right panel)
// ─────────────────────────────────────────────────────────────
async function fetchRGA(query, results) {
  const aiAns  = document.getElementById('ai-answer');
  const aiRec  = document.getElementById('ai-rec-txt');
  const model  = document.getElementById('model-select')?.value ?? 'coveo-rga';

  if (aiAns) { aiAns.textContent = '✦ Thinking…'; aiAns.className = 'ai-ans loading'; aiAns.style.display = ''; }
  if (aiRec) aiRec.textContent = 'Generating recommendation…';

  try {
    let answer;
    if (model === 'coveo-rga') {
      const resp = await fetch('/api/rga-coveo', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ query }),
      });
      const data = await resp.json();
      answer = data.answer ?? '—';
    } else {
      const context = results.slice(0, 5).map(r => ({
        title:   r.title ?? '',
        excerpt: r.raw?.excerpt ?? r.excerpt ?? '',
      }));
      const resp = await fetch('/api/rga', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ query, context }),
      });
      const data = await resp.json();
      answer = data.answer ?? '—';
    }

    if (aiAns) {
      aiAns.textContent = `✦ ${answer}`;
      aiAns.className = 'ai-ans';
      aiAns.style.display = '';
    }
    if (aiRec) aiRec.textContent = `"${answer}"`;
  } catch (_) {
    if (aiAns) { aiAns.textContent = '(AI answer unavailable)'; aiAns.style.display = ''; }
    if (aiRec)   aiRec.textContent = '(unavailable)';
  }
}

// ─────────────────────────────────────────────────────────────
// 17. Model selector — notify Flask
// ─────────────────────────────────────────────────────────────
function wireModelSelector() {
  document.getElementById('model-select')?.addEventListener('change', async e => {
    try {
      await fetch('/api/set-model', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ model: e.target.value }),
      });
    } catch (_) { /* non-fatal */ }
  });
}

// ─────────────────────────────────────────────────────────────
// 18. Boot
// ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  buildTypeGrid();
  wireGenList();
  wireMapToggles();
  wireSearchBar();
  wireModelSelector();

  await initAtomic();
  wireEngineSubscription();
});
