/**
 * Pokédex V2B — Dark Dashboard
 * Drives the 3-column layout:
 *   - Left sidebar:  type chips + generation list → Coveo facet filters
 *   - Center:        search bar → Coveo results → photo card → similar Pokémon
 *   - Right panel:   stats · moves · type effectiveness · RGA recommendation
 */

import { TYPE_COLORS, TYPE_CHART, ALL_TYPES, typeMultiplier, multLabel,
         pokeSlug, pokemonDbArtworkUrl, pokemonDbSpriteUrl,
         fetchPokeData, fetchMoveMeta,
         renderStatBars, renderMovesTable, renderTypeEffectiveness,
         updatePhotoCard, setPanelHeader, matchupSummary,
         STAT_KEYS } from './modules/pokemon-panel.js';

// Generation → Roman numeral mapping (used for Coveo facet values)
const GEN_MAP = {
  I: 'gen-i', II: 'gen-ii', III: 'gen-iii', IV: 'gen-iv',
  V: 'gen-v', VI: 'gen-vi', VII: 'gen-vii', VIII: 'gen-viii', IX: 'gen-ix',
};

// ─────────────────────────────────────────────────────────────
// PokéAPI game version → { gen (number 1–9), region label }
// Used to group encounter locations by generation for the map card.
// ─────────────────────────────────────────────────────────────
// PokéAPI version name → { gen, region }
// Rules:
//  - Remakes are filed under their ORIGINAL generation so e.g. HGSS Johto
//    encounters appear as "Gen II · Johto" not "Gen IV · Johto".
//  - FRLG / BDSP / ORAS / LGPE are likewise under their source gen.
//  - This means a toggle button for "Gen II · Johto" correctly aggregates
//    both original GSC encounters AND HGSS encounter data.
const VERSION_GEN = {
  // Gen I — Kanto
  'red':              { gen: 1, region: 'Kanto' },
  'blue':             { gen: 1, region: 'Kanto' },
  'yellow':           { gen: 1, region: 'Kanto' },
  'red-japan':        { gen: 1, region: 'Kanto' },
  'green-japan':      { gen: 1, region: 'Kanto' },
  'firered':          { gen: 1, region: 'Kanto' },   // FRLG = Kanto remake
  'leafgreen':        { gen: 1, region: 'Kanto' },
  'lets-go-pikachu':  { gen: 1, region: 'Kanto' },   // LGPE = Kanto remake
  'lets-go-eevee':    { gen: 1, region: 'Kanto' },
  // Gen II — Johto
  'gold':             { gen: 2, region: 'Johto' },
  'silver':           { gen: 2, region: 'Johto' },
  'crystal':          { gen: 2, region: 'Johto' },
  'heartgold':        { gen: 2, region: 'Johto' },   // HGSS = Johto remake
  'soulsilver':       { gen: 2, region: 'Johto' },
  // Gen III — Hoenn
  'ruby':             { gen: 3, region: 'Hoenn' },
  'sapphire':         { gen: 3, region: 'Hoenn' },
  'emerald':          { gen: 3, region: 'Hoenn' },
  'omega-ruby':       { gen: 3, region: 'Hoenn' },   // ORAS = Hoenn remake
  'alpha-sapphire':   { gen: 3, region: 'Hoenn' },
  // Gen IV — Sinnoh
  'diamond':          { gen: 4, region: 'Sinnoh' },
  'pearl':            { gen: 4, region: 'Sinnoh' },
  'platinum':         { gen: 4, region: 'Sinnoh' },
  'brilliant-diamond':{ gen: 4, region: 'Sinnoh' },  // BDSP = Sinnoh remake
  'shining-pearl':    { gen: 4, region: 'Sinnoh' },
  // Gen V — Unova
  'black':            { gen: 5, region: 'Unova' },
  'white':            { gen: 5, region: 'Unova' },
  'black-2':          { gen: 5, region: 'Unova' },
  'white-2':          { gen: 5, region: 'Unova' },
  // Gen VI — Kalos / Hoenn (ORAS)
  'x':                { gen: 6, region: 'Kalos' },
  'y':                { gen: 6, region: 'Kalos' },
  // Gen VII — Alola
  'sun':              { gen: 7, region: 'Alola' },
  'moon':             { gen: 7, region: 'Alola' },
  'ultra-sun':        { gen: 7, region: 'Alola' },
  'ultra-moon':       { gen: 7, region: 'Alola' },
  // Gen VIII — Galar / Hisui
  'sword':            { gen: 8, region: 'Galar' },
  'shield':           { gen: 8, region: 'Galar' },
  'legends-arceus':   { gen: 8, region: 'Hisui' },
  // Gen IX — Paldea
  'scarlet':          { gen: 9, region: 'Paldea' },
  'violet':           { gen: 9, region: 'Paldea' },
};

// Region → best available map image (Bulbapedia archives — confirmed live)
// Preference: newest high-quality remake > original, artwork > schematic map
const REGION_MAP_IMG = {
  'Kanto':  'https://archives.bulbagarden.net/media/upload/d/d4/FRLG_Kanto.png',
  'Johto':  'https://archives.bulbagarden.net/media/upload/c/c2/HGSS_JohtoKanto.jpg',
  'Hoenn':  'https://archives.bulbagarden.net/media/upload/8/80/Hoenn_ORAS_Map.png',
  'Sinnoh': 'https://archives.bulbagarden.net/media/upload/0/08/Sinnoh_BDSP_artwork.png',
  'Unova':  'https://archives.bulbagarden.net/media/upload/0/01/Unova_B2W2.png',
  'Kalos':  'https://archives.bulbagarden.net/media/upload/b/b1/Kalos_Pok%C3%A9dex_map.png',
  'Alola':  'https://archives.bulbagarden.net/media/upload/0/0b/Alola_USUM_artwork.png',
  'Galar':  'https://archives.bulbagarden.net/media/upload/c/ce/Galar_artwork.png',
  'Hisui':  'https://archives.bulbagarden.net/media/upload/2/22/Legends_Arceus_Hisui.png',
  'Paldea': 'https://archives.bulbagarden.net/media/upload/f/fd/Paldea_artwork.png',
};

// Regions that have an interactive PokéMaps page (pokemaps.net)
// Deep-link: https://pokemaps.net/pokemon/{pokemonName}
const POKEMAPS_REGIONS = new Set(['Kanto', 'Johto', 'Hoenn', 'Paldea']);

// Gen number → label shown on toggle buttons
const GEN_LABEL = {
  1: 'Gen I', 2: 'Gen II', 3: 'Gen III', 4: 'Gen IV', 5: 'Gen V',
  6: 'Gen VI', 7: 'Gen VII', 8: 'Gen VIII', 9: 'Gen IX',
};

// Pokémon's origin generation (from Coveo `generation` field like "gen-i")
// → number, for defaulting the map toggle
const ORIGIN_GEN_NUM = {
  'gen-i': 1, 'gen-ii': 2, 'gen-iii': 3, 'gen-iv': 4,
  'gen-v': 5, 'gen-vi': 6, 'gen-vii': 7, 'gen-viii': 8, 'gen-ix': 9,
};

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
  // Clear any active-pokemon type highlighting when the user manually filters
  clearTypeHighlight();

  const on = chip.classList.toggle('on');
  if (on) _activeTypes.add(type.toLowerCase());
  else    _activeTypes.delete(type.toLowerCase());

  _selectedIndex = 0;
  renderFiltered({ autoSelect: true });
}

/**
 * Highlight the type chips that match the active Pokémon's types.
 * All other chips are dimmed. Resets when user manually clicks a chip.
 * @param {string[]} types  - e.g. ['fire', 'flying']
 */
function highlightActiveTypes(types) {
  const typeSet = new Set(types.map(t => t.toLowerCase()));
  document.querySelectorAll('.tchip').forEach(chip => {
    const t = chip.dataset.type.toLowerCase();
    if (typeSet.has(t)) {
      chip.classList.add('active');
      chip.classList.remove('dimmed');
    } else {
      chip.classList.add('dimmed');
      chip.classList.remove('active');
    }
  });
}

function clearTypeHighlight() {
  document.querySelectorAll('.tchip').forEach(chip => {
    chip.classList.remove('active', 'dimmed');
  });
}

/**
 * Generation number for a national-dex id. The Coveo index has no `generation`
 * field, so the sidebar used to fall back to the hardcoded "Gen I" row for
 * every Pokémon — Miraidon included. Deriving it from the dex number is exact.
 */
function genNumberFromId(id) {
  const bounds = [151, 251, 386, 493, 649, 721, 809, 905, 1025];
  for (let i = 0; i < bounds.length; i++) if (id <= bounds[i]) return i + 1;
  return null;
}

const GEN_ROMAN = ['I','II','III','IV','V','VI','VII','VIII','IX'];

/** Highlight the generation row this Pokémon actually belongs to. */
function highlightActiveGenerationById(id) {
  const n = genNumberFromId(id);
  const roman = n ? GEN_ROMAN[n - 1] : null;
  document.querySelectorAll('.gen-item').forEach(item => {
    const match = roman && item.dataset.gen === roman;
    item.classList.toggle('active', !!match);
    item.classList.toggle('dimmed', !match);
    // `on` means "filter applied"; keep it independent of this indicator.
    if (!_activeGen) item.classList.remove('on');
  });
}

function clearGenHighlight() {
  document.querySelectorAll('.gen-item').forEach(item => {
    item.classList.remove('active', 'dimmed');
  });
}

function updateAdvancedQuery(aq) {
  // The Coveo index backing this app is a plain web crawl of pokemondb.net — it
  // carries no @type1/@type2 fields, so an advanced query can never filter on
  // them. Previously the fallback appended the AQ string to the *query text*,
  // which corrupted the query, widened recall (96 → 500 results) and
  // accumulated on every click. Type filtering is now done client-side in
  // applyTypeFilter() against the PokéAPI types we already fetch.
  //
  // If the Headless action ever becomes reachable AND the fields get indexed,
  // this is where server-side faceting would go.
  const engine = document.querySelector('atomic-search-interface')?.engine;
  const updateAQ = engine?.actions?.query?.updateAdvancedSearchQueries;
  if (typeof updateAQ !== 'function') return;   // no-op, and leaves q untouched
  try {
    engine.dispatch(updateAQ({ aq }));
    engine.executeFirstSearch?.();
  } catch (_) { /* never fall back to mutating the query text */ }
}

// ─────────────────────────────────────────────────────────────
// 2. Generation list wiring
// ─────────────────────────────────────────────────────────────
function wireGenList() {
  document.querySelectorAll('.gen-item').forEach(item => {
    item.addEventListener('click', () => {
      const gen = item.dataset.gen;
      const wasOn = item.classList.contains('on');
      document.querySelectorAll('.gen-item').forEach(i => i.classList.remove('on'));

      // Clicking the active generation again clears the filter.
      if (wasOn) {
        _activeGen = null;
      } else {
        item.classList.add('on');
        _activeGen = gen;
        clearGenHighlight();
      }

      // Filter the current result set rather than running `generation:gen-ii`
      // as a free-text query — that matched page prose and returned mostly
      // wrong-generation Pokémon while looking like it had worked.
      _selectedIndex = 0;
      renderFiltered({ autoSelect: true });
    });
  });
}

// ─────────────────────────────────────────────────────────────
// 3. Map card — encounters grouped by gen, dynamic toggle buttons
// ─────────────────────────────────────────────────────────────

// Region name → location-area prefix(es) that belong to it.
// PokéAPI area names are prefixed by region (e.g. "kanto-route-2-...",
// "johto-route-30-..."). A handful of areas use different conventions.
const REGION_AREA_PREFIXES = {
  'Kanto':  ['kanto-', 'viridian-', 'pallet-', 'pewter-', 'cerulean-', 'vermilion-',
             'lavender-', 'celadon-', 'fuchsia-', 'saffron-', 'cinnabar-', 'one-island-',
             'two-island-', 'three-island-', 'four-island-', 'five-island-', 'six-island-',
             'seven-island-', 'berry-forest-', 'bond-bridge-', 'pattern-bush-',
             'mt-ember-', 'lost-cave-', 'memorial-pillar-'],
  'Johto':  ['johto-', 'new-bark-', 'cherrygrove-', 'violet-city-', 'azalea-', 'goldenrod-',
             'ecruteak-', 'olivine-', 'cianwood-', 'mahogany-', 'blackthorn-', 'safari-zone-johto',
             'ilex-forest-', 'national-park-', 'mt-mortar-', 'lake-of-rage-', 'mt-silver-',
             'bell-tower-', 'burned-tower-', 'tin-tower-', 'whirl-islands-', 'slowpoke-well-',
             'union-cave-', 'ruins-of-alph-', 'dark-cave-', 'ice-path-', 'dragons-den-',
             'mt-moon-johto', 'unknown-all-bugs-'],
  'Hoenn':  ['hoenn-', 'littleroot-', 'oldale-', 'petalburg-', 'rustboro-', 'dewford-',
             'slateport-', 'mauville-', 'verdanturf-', 'fallarbor-', 'lavaridge-', 'fortree-',
             'lilycove-', 'mossdeep-', 'sootopolis-', 'ever-grande-', 'battle-frontier-hoenn',
             'sky-pillar-', 'cave-of-origin-', 'seafloor-cavern-', 'mt-chimney-',
             'fiery-path-', 'meteor-falls-', 'rusturf-tunnel-', 'granite-cave-',
             'desert-ruins-', 'island-cave-', 'ancient-tomb-', 'shoal-cave-',
             'new-mauville-', 'abandoned-ship-', 'sea-mauville-', 'mirage-'],
  'Sinnoh': ['sinnoh-', 'twinleaf-', 'sandgem-', 'jubilife-', 'oreburgh-', 'floaroma-',
             'eterna-', 'hearthome-', 'solaceon-', 'veilstone-', 'pastoria-', 'celestic-',
             'canalave-', 'snowpoint-', 'sunyshore-', 'pokemon-league-sinnoh',
             'lake-verity-', 'lake-valor-', 'lake-acuity-', 'mt-coronet-',
             'great-marsh-', 'fuego-ironworks-', 'old-chateau-', 'iron-island-',
             'snowpoint-temple-', 'stark-mountain-', 'sendoff-spring-', 'turnback-cave-',
             'wayward-cave-', 'ravaged-path-', 'oreburgh-mine-', 'valley-windworks-'],
  'Unova':  ['unova-', 'nuvema-', 'accumula-', 'striaton-', 'nacrene-', 'castelia-',
             'nimbasa-', 'driftveil-', 'mistralton-', 'icirrus-', 'opelucid-', 'lacunosa-',
             'undella-', 'black-city-', 'white-forest-', 'anville-', 'floccesy-',
             'aspertia-', 'virbank-', 'humilau-', 'lentimas-', 'reversal-mountain-',
             'relic-castle-', 'twist-mountain-', 'dragonspiral-tower-', 'moor-of-icirrus-',
             'giant-chasm-', 'victory-road-unova', 'abundant-shrine-', 'nature-preserve-'],
  'Kalos':  ['kalos-', 'vaniville-', 'aquacorde-', 'santalune-', 'lumiose-', 'camphrier-',
             'ambrette-', 'cyllage-', 'geosenge-', 'shalour-', 'azure-bay-', 'coumarine-',
             'laverre-', 'dendemille-', 'anistar-', 'couriway-', 'snowbelle-',
             'pokemon-village-', 'victory-road-kalos', 'kiloude-', 'terminus-cave-'],
  'Alola':  ['alola-', 'melemele-', 'akala-', 'ula-ula-', 'poni-', 'lush-jungle-',
             'vast-poni-canyon-', 'resolution-cave-', 'ruins-of-conflict-',
             'ruins-of-life-', 'ruins-of-abundance-', 'ruins-of-hope-',
             'mount-hokulani-', 'po-town-', 'aether-'],
  'Galar':  ['galar-', 'postwick-', 'wedgehurst-', 'motostoke-', 'turffield-',
             'hulbury-', 'hammerlocke-', 'stow-on-side-', 'ballonlea-', 'circhester-',
             'spikemuth-', 'wyndon-', 'wild-area-', 'rolling-fields-', 'dappled-grove-',
             'watchtower-ruins-', 'east-lake-axewell-', 'west-lake-axewell-',
             'axew-s-eye-', 'south-lake-miloch-', 'motostoke-riverbank-',
             'bridge-field-', 'stony-wilderness-', 'dusty-bowl-', 'giant-s-mirror-',
             'hammerlocke-hills-', 'giant-s-cap-', 'lake-of-outrage-',
             'isle-of-armor-', 'crown-tundra-'],
  'Hisui':  ['hisui-', 'jubilife-village-', 'obsidian-fieldlands-', 'crimson-mirelands-',
             'cobalt-coastlands-', 'coronet-highlands-', 'alabaster-icelands-'],
  'Paldea': ['paldea-', 'cabo-poco-', 'los-platos-', 'mesagoza-', 'artazon-',
             'levincia-', 'cascarrafa-', 'medali-', 'montenevera-', 'alfornada-',
             'glaseado-', 'area-zero-'],
};

/**
 * Return true if a PokéAPI location-area name belongs to the given region.
 * Falls back to permissive (true) so unknown areas are never silently dropped.
 */
function areaMatchesRegion(areaName, region) {
  const prefixes = REGION_AREA_PREFIXES[region];
  if (!prefixes) return true;  // unknown region → show everything
  const lower = areaName.toLowerCase();
  return prefixes.some(p => lower.startsWith(p));
}

/**
 * Fetch encounters from PokéAPI and group by (gen, region) pairs.
 *
 * Key insight: a game version maps to exactly one gen+region. HGSS → gen 2 Johto.
 * Within that bucket, we only include location areas whose name actually belongs
 * to that region (e.g. johto-route-* yes, kanto-route-* no — even though the
 * game lets you visit both, the encounter belongs to its region's geography).
 *
 * Returns: Map<"gen:region", { gen, region, locations: string[] }>
 *   sorted by gen asc, then region alphabetically.
 */
async function fetchLocationsByGen(pokemonId) {
  try {
    const r = await fetch(`https://pokeapi.co/api/v2/pokemon/${pokemonId}/encounters`);
    if (!r.ok) return new Map();
    const data = await r.json();

    // group: "gen:region" → Set of matching location area names
    const grouped = new Map();
    for (const entry of data) {
      const areaName = entry.location_area?.name ?? '';
      if (!areaName) continue;
      for (const vd of entry.version_details) {
        const vInfo = VERSION_GEN[vd.version.name];
        if (!vInfo) continue;
        // Only add this area if it actually belongs to this region
        if (!areaMatchesRegion(areaName, vInfo.region)) continue;
        const key = `${vInfo.gen}:${vInfo.region}`;
        if (!grouped.has(key)) grouped.set(key, { gen: vInfo.gen, region: vInfo.region, locs: new Set() });
        grouped.get(key).locs.add(areaName);
      }
    }

    // Sort: gen asc, then region name asc within same gen
    const sorted = [...grouped.entries()].sort(([, a], [, b]) =>
      a.gen !== b.gen ? a.gen - b.gen : a.region.localeCompare(b.region)
    );

    const result = new Map();
    for (const [key, { gen, region, locs }] of sorted) {
      result.set(key, {
        gen,
        region,
        locations: [...locs].map(n =>
          n.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
        ).sort(),
      });
    }
    return result;
  } catch { return new Map(); }
}

// Module-level state: encounter slots + Pokémon name for the active selection
let _currentEncountersByGen = new Map();   // Map<"gen:region", {...}>
let _currentPokemonName = '';

/**
 * Build the gen toggle buttons from encounter data and wire their clicks.
 * Default: prefer the Pokémon's origin gen (lowest region key for that gen),
 * else the first entry overall.
 */
function buildMapToggles(encountersByGen, originGen) {
  const togglesEl = document.getElementById('map-gen-toggles');
  if (!togglesEl) return;

  const entries = [...encountersByGen.keys()];  // already sorted

  if (!entries.length) {
    togglesEl.innerHTML = '<span class="gtbtn-none">No wild encounter data</span>';
    renderMapForKey(null);
    return;
  }

  // Pick which key to activate: first key whose gen matches originGen, else first
  const defaultKey = entries.find(k => encountersByGen.get(k).gen === originGen) ?? entries[0];

  togglesEl.innerHTML = entries.map(key => {
    const { gen, region } = encountersByGen.get(key);
    return `<div class="gtbtn${key === defaultKey ? ' on' : ''}" data-mapkey="${key}">`
         + `<span class="gtbtn-gen">${GEN_LABEL[gen] ?? `Gen ${gen}`}</span>`
         + `<span class="gtbtn-region">${region}</span>`
         + `</div>`;
  }).join('');

  togglesEl.querySelectorAll('.gtbtn').forEach(btn => {
    btn.addEventListener('click', () => {
      togglesEl.querySelectorAll('.gtbtn').forEach(b => b.classList.remove('on'));
      btn.classList.add('on');
      renderMapForKey(btn.dataset.mapkey);
    });
  });

  renderMapForKey(defaultKey);
}

/**
 * Render the map image + location pills for the given "gen:region" key.
 */
function renderMapForKey(key) {
  const data   = key ? _currentEncountersByGen.get(key) : null;
  const pills  = document.getElementById('map-pills');
  const wrap   = document.getElementById('map-region-wrap');
  const img    = document.getElementById('map-region-img');
  const label  = document.getElementById('map-region-label');
  const subEl  = document.getElementById('map-sub');

  if (!data) {
    if (pills) pills.innerHTML = '<span class="mpill">No encounter data</span>';
    if (wrap)  wrap.style.display = 'none';
    if (subEl) subEl.innerHTML = '';
    return;
  }

  const { gen, region, locations } = data;

  // Region map image — Bulbapedia high-res
  const mapUrl = REGION_MAP_IMG[region];
  if (wrap && img && mapUrl) {
    // Only reload if the source changed (avoids flicker on pill-only updates)
    if (img.dataset.region !== region) {
      img.src = mapUrl;
      img.dataset.region = region;
      // Reset pan position when the region changes
      img.style.transform = 'translate(0px, 0px)';
      img.dataset.panX = '0';
      img.dataset.panY = '0';
    }
    img.style.display = '';
    if (label) label.textContent = region;
    wrap.style.display = '';
  } else if (wrap) {
    wrap.style.display = 'none';
  }

  // Location pills — cap at 5 to keep the card compact
  if (pills) {
    const shown = locations.slice(0, 5);
    const extra = locations.length - shown.length;
    pills.innerHTML = shown.map(loc => `<span class="mpill">${loc}</span>`).join('')
      + (extra > 0 ? `<span class="mpill mpill-more">+${extra} more</span>` : '');
  }

  // Sub-label with external link
  if (subEl) {
    const slug = _currentPokemonName.toLowerCase();
    const href = POKEMAPS_REGIONS.has(region) && slug
      ? `https://pokemaps.net/pokemon/${slug}`
      : `https://www.serebii.net/pokearth/${region.toLowerCase()}/`;
    const linkText = POKEMAPS_REGIONS.has(region) ? 'PokéMaps ↗' : 'Pokéarth ↗';
    subEl.innerHTML = `<a class="map-ext-link" href="${href}" target="_blank" rel="noopener">${linkText}</a>`;
  }
}

// Keep fetchLocationAreas as a thin shim (no longer called internally,
// but kept to avoid breaking any future callers)
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

  // Force Bulbasaur as the default on load — drives the full panel population
  // via the engine subscription (stats, moves, photo, etc.)
  dispatchSearch('bulbasaur');

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
  // An empty submit used to return the entire index (1031 results) headed by a
  // non-Pokémon listing page, while leaving the previous AI answer on screen.
  const text = String(q ?? '').trim();
  if (!text) return;
  const sb = document.querySelector('atomic-search-box');
  if (sb?.searchBox) {
    sb.searchBox.updateText(text);
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
// Tracks the result index the user has explicitly selected (or 0 for the
// auto-selected first result on a fresh search).  Used by both the engine
// subscription and renderResultsList so they always agree on which row is
// active and never clobber a user-chosen selection.
let _selectedIndex = 0;

function wireEngineSubscription() {
  const si = document.querySelector('atomic-search-interface');
  if (!si) return;

  let lastLoading = null;   // null = unknown; first state snapshot sets the baseline
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

      // Treat the very first snapshot as a baseline (don't fire yet);
      // fire on every true → false loading transition after that.
      if (lastLoading === null) { lastLoading = loading; return; }
      const justFinished = lastLoading === true && loading === false;
      lastLoading = loading;

      if (!justFinished) return;

      const queryChanged = query !== lastQuery;

      // New text query → reset selection and clear any active sidebar filters.
      // A user typing "bounsweet" with Poison still active should not get
      // 0 results — the filter chips belong to the previous search context.
      // Filter/facet update (same query) → keep whatever the user chose.
      if (queryChanged) {
        _selectedIndex = 0;
        lastQuery = query;
        // Clear type chips
        if (_activeTypes.size) {
          _activeTypes.clear();
          document.querySelectorAll('.tchip.on').forEach(c => c.classList.remove('on'));
        }
        // Clear generation filter
        if (_activeGen) {
          _activeGen = null;
          document.querySelectorAll('.gen-item.on').forEach(g => g.classList.remove('on'));
        }
      }

      _rawResults = results;
      _rawTotal   = total;
      renderFiltered({ autoSelect: !queryChanged });

      // Fire RGA only on new text searches
      if (queryChanged && query) {
        const q = document.getElementById('search-input');
        if (q && !q.value) q.value = query;
        fetchRGA(query, results);
      }
    });
  };

  trySubscribe();
}

// ─────────────────────────────────────────────────────────────
// 8. Client-side filtering + results list
//
// The Coveo index has no structured Pokémon fields (no @type1/@generation),
// so filtering happens here against the PokéAPI data we already fetch and
// cache for every result. This keeps the chips and generation rows honest:
// they either filter correctly or they do not claim to filter at all.
// ─────────────────────────────────────────────────────────────
let _rawResults = [];     // untouched results from the engine
let _rawTotal   = 0;
let _shownResults = [];   // what is actually rendered (post-filter)
const _activeTypes = new Set();
let   _activeGen   = null;   // 'I' … 'IX' or null

// National-dex ranges per generation — used to filter by generation without
// a Coveo `generation` field. PokéAPI ids match national dex for base species.
const GEN_RANGES = {
  I: [1, 151],    II: [152, 251],  III: [252, 386],
  IV: [387, 493], V: [494, 649],   VI: [650, 721],
  VII: [722, 809], VIII: [810, 905], IX: [906, 1025],
};

/** Resolve PokéAPI data for a result (cached by fetchPokeData). */
async function resultPoke(r) {
  return fetchPokeData(extractPokemonName(r.title));
}

/** Apply the active type/generation filters to the raw result set. */
async function computeFiltered() {
  if (!_activeTypes.size && !_activeGen) return _rawResults;
  const pokes = await Promise.all(_rawResults.map(resultPoke));
  return _rawResults.filter((r, i) => {
    const poke = pokes[i];
    if (!poke) return false;   // unverifiable while a filter is active → hide
    if (_activeTypes.size && !poke.types.some(t => _activeTypes.has(t.toLowerCase()))) return false;
    if (_activeGen) {
      const range = GEN_RANGES[_activeGen];
      if (!range || poke.id < range[0] || poke.id > range[1]) return false;
    }
    return true;
  });
}

/** Recompute the filtered list and repaint. */
async function renderFiltered({ autoSelect = false } = {}) {
  const filtering = _activeTypes.size > 0 || _activeGen !== null;
  const list = document.getElementById('results-list');
  if (list && filtering) {
    list.innerHTML = '<div class="ritem" style="color:#555;font-size:11px;padding:10px 12px;">Filtering…</div>';
  }
  _shownResults = await computeFiltered();
  renderResultsList(_shownResults, _rawTotal, filtering);

  if (_shownResults.length > 0) {
    const idx = Math.min(_selectedIndex, _shownResults.length - 1);
    selectResult(_shownResults[idx], autoSelect);
  }
}

function renderResultsList(results, total, filtering = false) {
  const list  = document.getElementById('results-list');
  const count = document.getElementById('result-count');
  if (!list) return;

  // Report what is actually reachable, not just what the index matched.
  // "736 found" next to 10 rows and no pager was misleading.
  if (count) {
    if (filtering) {
      count.textContent = `${results.length} of ${_rawResults.length} shown`;
    } else if (total) {
      count.textContent = results.length < total
        ? `showing ${results.length} of ${total}`
        : `${total} found`;
    } else {
      count.textContent = '—';
    }
  }

  if (!results.length) {
    list.innerHTML = filtering
      ? '<div class="ritem" style="color:#555;font-size:11px;padding:10px 12px;">No results match these filters</div>'
      : '<div class="ritem" style="color:#555;font-size:11px;padding:10px 12px;">No results found</div>';
    return;
  }

  const activeSel = Math.min(_selectedIndex, results.length - 1);

  list.innerHTML = results.map((r, i) => {
    const name = extractPokemonName(r.title);
    return `
      <div class="ritem${i === activeSel ? ' sel' : ''}" data-index="${i}">
        <span class="rname">${escapeHtml(name)}</span>
        <span class="rbadges" data-badges-for="${escapeHtml(name)}"></span>
        <a class="cmp-btn" href="/coach?compare=${encodeURIComponent(name.toLowerCase())}&with=pikachu"
           title="Compare in Coach" tabindex="-1">⇌</a>
      </div>`;
  }).join('');

  // Type badges come from PokéAPI (the Coveo index has no type fields), so
  // they are filled in asynchronously once the cached lookup resolves.
  results.forEach(r => {
    const name = extractPokemonName(r.title);
    fetchPokeData(name).then(poke => {
      if (!poke) return;
      const slot = list.querySelector(`[data-badges-for="${CSS.escape(name)}"]`);
      if (slot) slot.innerHTML = poke.types.map(t => typeBadgeHtml(t)).join('');
    });
  });

  list.querySelectorAll('.ritem').forEach(item => {
    item.addEventListener('click', () => {
      list.querySelectorAll('.ritem').forEach(i => i.classList.remove('sel'));
      item.classList.add('sel');
      _selectedIndex = parseInt(item.dataset.index, 10);
      const selected = results[_selectedIndex];
      selectResult(selected, false);
      fetchRGA(extractPokemonName(selected.title), results);
    });
  });

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
}

/** Escape text destined for innerHTML. */
function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
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
// Monotonic token: every selectResult call claims one, and re-checks it after
// each await. A slower earlier request can therefore no longer overwrite the
// panel with a stale Pokémon when the user searches rapidly.
let _selectToken = 0;
let _lastSelectedTypes = [];

/**
 * Blank every data panel and say so, rather than leaving the previous
 * Pokémon's stats sitting under a new name.
 */
function resetPanels(name) {
  const msg = `<div style="color:#666;font-size:11px;">No detailed data for ${escapeHtml(name)}</div>`;
  const set = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };

  set('stat-bars', msg);
  set('weak-chips',   '<span style="color:#555;font-size:11px;">—</span>');
  set('resist-chips', '<span style="color:#555;font-size:11px;">—</span>');
  set('strong-chips', '<span style="color:#555;font-size:11px;">—</span>');
  set('moves-tbody',
    `<tr><td colspan="3" style="color:#666;font-size:11px;text-align:center;padding:10px;">No move data for ${escapeHtml(name)}</td></tr>`);
  set('similar-grid', '<div class="sim-placeholder">—</div>');
  set('map-pills',    '<span class="mpill">No encounter data</span>');
  set('map-gen-toggles', '<span class="gtbtn-none">No wild encounter data</span>');

  const wrap = document.getElementById('map-region-wrap');
  if (wrap) wrap.style.display = 'none';
  const sub = document.getElementById('map-sub');
  if (sub) sub.innerHTML = '';

  // Name tags keep the Pokémon name but drop the stale type/number chips.
  const tags = document.getElementById('rp-tags');
  if (tags) tags.innerHTML = '';
  const rec = document.getElementById('ai-rec-txt');
  if (rec) rec.textContent = `No matchup data for ${name}`;
  const num = document.getElementById('photo-num');
  if (num) num.textContent = '';

  _currentEncountersByGen = new Map();
  _lastSelectedTypes = [];
  clearTypeHighlight();
  clearGenHighlight();
}

async function selectResult(result, autoSelect) {
  const name = extractPokemonName(result.title);
  if (!name || name.length < 2) return;

  const token = ++_selectToken;

  // Immediately update name labels
  setPhotoName(name, null);
  setPanelHeader(name, [], null, '');

  // ── Artwork from pokemondb.net (Coveo-indexed or CDN-derived) ──
  const artworkUrl = pokemonDbArtworkUrl(name, result.raw);
  updatePhotoCard(artworkUrl, name, null, '', '');

  // Header circle sprite — set before the PokéAPI await so it works even for
  // Pokémon PokéAPI does not know about.
  const headerSprite = document.getElementById('header-sprite');
  if (headerSprite) {
    headerSprite.alt = name;
    headerSprite.onload  = () => { headerSprite.style.opacity = '1'; };
    headerSprite.onerror = () => { headerSprite.style.opacity = '0'; };
    headerSprite.src = pokemonDbSpriteUrl(name);
  }

  // ── PokéAPI for stats / moves / types / location ──
  const poke = await fetchPokeData(name);
  if (token !== _selectToken) return;          // superseded by a newer selection

  if (!poke) {
    // Never leave the previous Pokémon's data under this one's name.
    resetPanels(name);
    return;
  }

  // Photo card — refresh number + glow once we have the id
  setPhotoName(name, poke.id);
  updatePhotoCard(artworkUrl, name, poke.id, poke.types[0], '');

  if (headerSprite && poke.sprite) {
    headerSprite.onload  = () => { headerSprite.style.opacity = '1'; };
    headerSprite.onerror = () => { /* keep pokemondb sprite already showing */ };
    headerSprite.src = poke.sprite;
  }

  // Right panel
  setPanelHeader(name, poke.types, poke.id, '');
  renderStatBars(poke.stats, '');
  renderMovesTable(poke.moves, poke.types, '');
  renderTypeEffectiveness(poke.types, '');
  _lastSelectedTypes = poke.types;
  renderMatchupLine(poke.types);

  // Sidebar highlights — only when the user is not actively filtering,
  // so the highlight never fights the filter state.
  if (!_activeTypes.size) highlightActiveTypes(poke.types);
  if (!_activeGen) highlightActiveGenerationById(poke.id);

  // Map location — derive the origin generation from the dex number, since the
  // Coveo index carries no `generation` field.
  const originGenNum = genNumberFromId(poke.id);
  _currentPokemonName = name;
  const encounters = await fetchLocationsByGen(poke.id);
  if (token !== _selectToken) return;          // superseded while fetching
  _currentEncountersByGen = encounters;
  buildMapToggles(_currentEncountersByGen, originGenNum);

  // Similar Pokémon (same primary type)
  renderSimilarPokemon(poke.types[0], name, token);
}

function setPhotoName(name, pokeId) {
  const nameEl = document.getElementById('photo-name');
  const numEl  = document.getElementById('photo-num');
  if (nameEl) nameEl.textContent = name;
  if (numEl && pokeId)  numEl.textContent = `#${String(pokeId).padStart(3, '0')}`;
  else if (numEl) numEl.textContent = '';
}

// ─────────────────────────────────────────────────────────────
// 15. Similar Pokémon — fetch 3 same-type Pokémon from PokéAPI
// ─────────────────────────────────────────────────────────────
async function renderSimilarPokemon(primaryType, excludeName, token) {
  const grid = document.getElementById('similar-grid');
  if (!grid) return;

  grid.innerHTML = '<div class="sim-placeholder">Loading…</div>';

  try {
    const t = primaryType.toLowerCase();
    const r = await fetch(`https://pokeapi.co/api/v2/type/${t}`);
    if (token !== undefined && token !== _selectToken) return;
    if (!r.ok) { grid.innerHTML = '<div class="sim-placeholder">—</div>'; return; }
    const data = await r.json();
    if (token !== undefined && token !== _selectToken) return;

    // Exclude alternate forms, but keep genuine species whose slug contains a
    // hyphen (ho-oh, porygon-z, type-null, tapu-koko, iron-valiant, great-tusk).
    // The previous allowlist used 'alolan/galarian/hisuian' where PokéAPI uses
    // 'alola/galar/hisui', so it matched nothing and dropped real Pokémon.
    const FORM_SUFFIXES = new Set([
      'mega','megax','megay','gmax','alola','galar','hisui','paldea','totem',
      'standard','zen','average','small','large','super','baile','pau','pompom',
      'sensu','midday','midnight','dusk','solo','school','amped','lowkey',
      'ice','noice','male','female','plant','sandy','trash','origin','altered',
      'sky','land','ordinary','resolute','aria','pirouette','blade','shield',
      'incarnate','therian','black','white','primal','complete','10','50',
      'red-striped','blue-striped','white-striped','single-strike','rapid-strike',
      'crowned','eternamax','hero','zero','curly','droopy','stretchy',
      'two-segment','three-segment','family-of-four','family-of-three',
      'green-plumage','blue-plumage','yellow-plumage','white-plumage',
      'four','roaming','starter','bloodmoon','teal','wellspring','hearthflame',
      'cornerstone','terastal','stellar',
    ]);
    const pool = (data.pokemon ?? [])
      .map(p => p.pokemon.name)
      .filter(n => n.toLowerCase() !== excludeName.toLowerCase())
      .filter(n => {
        const parts = n.split('-');
        if (parts.length === 1) return true;
        // Drop if ANY trailing segment is a known form marker
        return !parts.slice(1).some(seg => FORM_SUFFIXES.has(seg));
      });

    // Deterministic pick: the same Pokémon always yields the same three
    // suggestions, so the panel can be returned to and compared.
    const picked = stablePick(pool, 3, excludeName);
    if (!picked.length) {
      grid.innerHTML = '<div class="sim-placeholder">No similar Pokémon found</div>';
      return;
    }

    const cards = await Promise.all(picked.map(async name => ({
      name, poke: await fetchPokeData(name),
    })));
    if (token !== undefined && token !== _selectToken) return;

    grid.innerHTML = cards.map(({ name, poke }) => {
      const displayName = name.replace(/-/g, ' ')
        .split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
      // Badge each card with its OWN types, not the source Pokémon's — the old
      // version labelled Carkol (Rock/Fire) as "Fire" because Charizard is Fire.
      const badges = (poke?.types ?? [primaryType]).map(tp => {
        const c = TYPE_COLORS[tp.toLowerCase()] ?? { bg: '#444' };
        return `<span class="sim-type" style="background:${c.bg}33;color:${c.bg};border:1px solid ${c.bg}66">${tp.charAt(0).toUpperCase() + tp.slice(1)}</span>`;
      }).join('');
      return `
        <div class="sim-card" data-name="${escapeHtml(name)}">
          <img class="sim-sprite" src="${poke?.sprite ?? ''}"
               alt="${escapeHtml(displayName)}" onerror="this.style.display='none'" />
          <div class="sim-name">${escapeHtml(displayName)}</div>
          ${badges}
        </div>`;
    }).join('');

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

/**
 * Pick n items deterministically from arr, seeded by `seed`, so repeated
 * renders of the same Pokémon always produce the same suggestions.
 */
function stablePick(arr, n, seed) {
  let h = 2166136261;
  for (const ch of String(seed)) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
  const out = [];
  const used = new Set();
  for (let i = 0; i < n && used.size < arr.length; i++) {
    let idx = Math.abs(h) % arr.length;
    while (used.has(idx)) idx = (idx + 1) % arr.length;
    used.add(idx);
    out.push(arr[idx]);
    h = Math.imul(h ^ (h >>> 13), 16777619);
  }
  return out;
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
/**
 * Paint the computed matchup into the recommendation card, preserving any
 * model prose already there. Called by selectResult the moment types are known.
 */
function renderMatchupLine(types) {
  const aiRec = document.getElementById('ai-rec-txt');
  if (!aiRec) return;
  const summary = matchupSummary(types);
  if (!summary) return;
  const prose = aiRec.querySelector('.ai-prose')?.outerHTML ?? '';
  aiRec.innerHTML = `<span class="ai-calc">${escapeHtml(summary)}</span>` + prose;
}

let _rgaToken = 0;

async function fetchRGA(query, results) {
  const aiAns  = document.getElementById('ai-answer');
  const aiRec  = document.getElementById('ai-rec-txt');
  const model  = document.getElementById('model-select')?.value ?? 'coveo-rga';
  const token  = ++_rgaToken;

  // The deterministic matchup line is rendered by selectResult(), which is the
  // only place that knows the selected Pokémon's types. fetchRGA is dispatched
  // from the engine subscription before that resolves, so it must not read
  // _lastSelectedTypes here — it re-reads it after the await, by which time
  // selectResult has run.
  if (aiAns) { aiAns.textContent = '✦ Thinking…'; aiAns.className = 'ai-ans loading'; aiAns.style.display = ''; }

  try {
    let answer;
    if (model === 'coveo-rga') {
      const resp = await fetch('/api/rga-coveo', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ query }),
      });
      const data = await resp.json();
      answer = data.answer ?? '';
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
      answer = data.answer ?? '';
    }
    if (token !== _rgaToken) return;   // a newer query superseded this one

    const summary = matchupSummary(_lastSelectedTypes ?? []);

    // Treat the model's non-answers as absent rather than printing them raw.
    const empty = !answer
      || /^\(no answer generated\)/i.test(answer)
      || /^\(RGA model did not trigger/i.test(answer)
      || /^\((CRGA|Coveo|Stream)/i.test(answer);

    if (aiAns) {
      aiAns.className = 'ai-ans';
      aiAns.style.display = '';
      if (empty) {
        aiAns.textContent = summary
          ? `✦ ${summary}`
          : '✦ No write-up for this query — try a Pokémon name.';
      } else {
        aiAns.textContent = `✦ ${answer}`;
      }
    }
    if (aiRec) {
      const calc = summary ? `<span class="ai-calc">${escapeHtml(summary)}</span>` : '';
      const prose = empty ? '' : `<span class="ai-prose">“${escapeHtml(answer)}”</span>`;
      aiRec.innerHTML = calc + prose || '—';
    }
  } catch (_) {
    if (token !== _rgaToken) return;
    // The computed matchup still stands even when the model is unreachable.
    const summary = matchupSummary(_lastSelectedTypes ?? []);
    if (aiAns) {
      aiAns.className = 'ai-ans';
      aiAns.style.display = '';
      aiAns.textContent = summary ? `✦ ${summary}` : '✦ (AI answer unavailable)';
    }
    if (aiRec) aiRec.innerHTML = summary
      ? `<span class="ai-calc">${escapeHtml(summary)}</span>`
      : '(unavailable)';
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
// 18. Map drag-to-pan
// Mouse and touch drag inside the map-region-wrap container.
// The image is larger than the container; overflow is hidden in CSS.
// ─────────────────────────────────────────────────────────────
function wireMapPan() {
  const wrap = document.getElementById('map-region-wrap');
  const img  = document.getElementById('map-region-img');
  if (!wrap || !img) return;

  let dragging = false;
  let startX = 0, startY = 0;
  let originX = 0, originY = 0;

  function clamp(val, min, max) { return Math.max(min, Math.min(max, val)); }

  function panTo(x, y) {
    // img is rendered at 180% width via CSS; measure the actual rendered size
    const imgRect  = img.getBoundingClientRect();
    const wrapRect = wrap.getBoundingClientRect();
    const overX = Math.max(0, imgRect.width  - wrapRect.width)  / 2;
    const overY = Math.max(0, imgRect.height - wrapRect.height) / 2;
    const cx = clamp(x, -overX, overX);
    const cy = clamp(y, -overY, overY);
    img.style.transform = `translate(${cx}px, ${cy}px)`;
    img.dataset.panX = String(cx);
    img.dataset.panY = String(cy);
  }

  // Mouse
  wrap.addEventListener('mousedown', e => {
    dragging = true;
    startX = e.clientX;
    startY = e.clientY;
    originX = parseFloat(img.dataset.panX) || 0;
    originY = parseFloat(img.dataset.panY) || 0;
    wrap.style.cursor = 'grabbing';
    e.preventDefault();
  });
  window.addEventListener('mousemove', e => {
    if (!dragging) return;
    panTo(originX + (e.clientX - startX), originY + (e.clientY - startY));
  });
  window.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    wrap.style.cursor = 'grab';
  });

  // Touch
  wrap.addEventListener('touchstart', e => {
    const t = e.touches[0];
    dragging = true;
    startX = t.clientX;
    startY = t.clientY;
    originX = parseFloat(img.dataset.panX) || 0;
    originY = parseFloat(img.dataset.panY) || 0;
    e.preventDefault();
  }, { passive: false });
  wrap.addEventListener('touchmove', e => {
    if (!dragging) return;
    const t = e.touches[0];
    panTo(originX + (t.clientX - startX), originY + (t.clientY - startY));
    e.preventDefault();
  }, { passive: false });
  wrap.addEventListener('touchend', () => { dragging = false; });
}

// ─────────────────────────────────────────────────────────────
// 19. Boot
// ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  buildTypeGrid();
  wireGenList();
  wireSearchBar();
  wireModelSelector();
  wireMapPan();

  // Wire subscription BEFORE initAtomic so the trySubscribe loop can catch
  // the engine as soon as it exists, and picks up the executeFirstSearch result.
  wireEngineSubscription();
  await initAtomic();
});
