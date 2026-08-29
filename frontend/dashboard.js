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
// PokéDB artwork helpers
// ─────────────────────────────────────────────────────────────

/**
 * Return the pokemondb.net high-res artwork URL for a given name.
 * Falls back through Coveo-indexed image_url → local file.
 * PokeAPI is NOT used for the artwork image.
 *
 * @param {string} name      - Pokémon name (any case)
 * @param {object} [raw]     - Coveo result.raw (may contain image_url)
 * @returns {string}
 */
function pokemonDbArtworkUrl(name, raw) {
  const slug = name.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-');
  // Prefer the URL Coveo already indexed from pokemondb.net
  if (raw?.image_url) return raw.image_url;
  // Derive directly from pokemondb CDN (large artwork)
  return `https://img.pokemondb.net/artwork/large/${slug}.jpg`;
}

/**
 * Return the pokemondb.net sprite URL (used for the sidebar header icon — V2).
 * These are the "home" normal sprites which are small and load fast.
 *
 * @param {string} name - Pokémon name
 * @returns {string}
 */
function pokemonDbSpriteUrl(name) {
  const slug = name.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-');
  return `https://img.pokemondb.net/sprites/home/normal/${slug}.png`;
}

// ─────────────────────────────────────────────────────────────
// PokéAPI cache  (still used for stats, moves, types, location)
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
  // Clear any active-pokemon type highlighting when the user manually filters
  clearTypeHighlight();
  clearGenHighlight();

  const wasOn = chip.classList.toggle('on');
  // Drive Coveo facet via the engine
  const si = document.querySelector('atomic-search-interface');
  const engine = si?.engine;
  if (!engine) return;

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
 * Highlight generation rows that match the active Pokémon's generation(s).
 * The Coveo `generation` field is a string like "gen-i" or comma-separated.
 * @param {string|string[]} genField - raw.generation value from Coveo result
 */
function highlightActiveGenerations(genField) {
  if (!genField) { clearGenHighlight(); return; }

  // Normalise: Coveo may return a string or array; split on commas/spaces
  const raw = Array.isArray(genField) ? genField : [genField];
  const genSet = new Set(
    raw.flatMap(v => v.split(/[,\s]+/))
       .map(v => v.toLowerCase().trim())
       .filter(Boolean)
  );

  // Build a reverse lookup: GEN_MAP key → Coveo gen value  (e.g. 'I' → 'gen-i')
  document.querySelectorAll('.gen-item').forEach(item => {
    const coveoVal = GEN_MAP[item.dataset.gen] ?? '';
    if (genSet.has(coveoVal)) {
      item.classList.add('active');
      item.classList.remove('dimmed');
    } else {
      item.classList.add('dimmed');
      item.classList.remove('active');
    }
  });
}

function clearGenHighlight() {
  document.querySelectorAll('.gen-item').forEach(item => {
    item.classList.remove('active', 'dimmed');
  });
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

      // New text query → reset selection to the top result.
      // Filter/facet update (same query) → keep whatever index the user chose.
      if (queryChanged) {
        _selectedIndex = 0;
        lastQuery = query;
      }

      // Render results list, honouring the current selection index.
      renderResultsList(results, total);

      // Auto-select top result on a fresh search; on a filter update just
      // re-select whatever _selectedIndex already points at so the panel
      // stays in sync if the result set shifted.
      if (results.length > 0) {
        const idx = Math.min(_selectedIndex, results.length - 1);
        selectResult(results[idx], !queryChanged);
      }

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

  // Use _selectedIndex as source of truth for which row is highlighted,
  // rather than always stamping index 0 as selected.
  const activeSel = Math.min(_selectedIndex, results.length - 1);

  list.innerHTML = results.map((r, i) => {
    const name  = extractPokemonName(r.title);
    const type1 = r.raw?.type1 ?? '';
    const type2 = r.raw?.type2 ?? '';
    return `
      <div class="ritem${i === activeSel ? ' sel' : ''}" data-index="${i}">
        <span class="rname">${name}</span>
        ${typeBadgeHtml(type1)}
        ${type2 ? typeBadgeHtml(type2) : ''}
      </div>`;
  }).join('');

  // Wire click handlers — update _selectedIndex so the subscription
  // knows the user's choice if a subsequent filter update arrives.
  list.querySelectorAll('.ritem').forEach(item => {
    item.addEventListener('click', () => {
      list.querySelectorAll('.ritem').forEach(i => i.classList.remove('sel'));
      item.classList.add('sel');
      _selectedIndex = parseInt(item.dataset.index, 10);
      selectResult(results[_selectedIndex], false);
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

  // ── Artwork from pokemondb.net (Coveo-indexed or CDN-derived) ──
  // PokeAPI is NOT used for the main artwork image.
  const artworkUrl = pokemonDbArtworkUrl(name, result.raw);
  updatePhotoCard(artworkUrl, name, null, result.raw?.type1 ?? '');

  // V2: set the header circle sprite immediately from pokemondb.
  // This runs unconditionally — before PokeAPI — so it works even
  // for Pokémon PokeAPI doesn't know about yet (e.g. new Gen IX entries).
  const headerSprite = document.getElementById('header-sprite');
  if (headerSprite) {
    const spriteUrl = pokemonDbSpriteUrl(name);
    headerSprite.alt = name;
    headerSprite.onload  = () => { headerSprite.style.opacity = '1'; };
    headerSprite.onerror = () => { headerSprite.style.opacity = '0'; };
    headerSprite.src = spriteUrl;
  }

  // ── PokéAPI for stats / moves / types / location ──
  const poke = await fetchPokeData(name);
  if (!poke) return;

  // Photo card — refresh number + glow once we have the id
  setPhotoName(name, poke.id);
  updatePhotoCard(artworkUrl, name, poke.id, poke.types[0]);

  // If PokeAPI has a sprite, upgrade the header circle to it
  if (headerSprite && poke.sprite) {
    headerSprite.onload  = () => { headerSprite.style.opacity = '1'; };
    headerSprite.onerror = () => { /* keep pokemondb sprite already showing */ };
    headerSprite.src = poke.sprite;
  }

  // Right panel
  setRightPanelName(name, poke.types, poke.id);
  renderStatBars(poke.stats);
  renderMovesTable(poke.moves, poke.types);
  renderTypeEffectiveness(poke.types);

  // Sidebar highlights — show which types & generation(s) belong to this Pokémon
  highlightActiveTypes(poke.types);
  highlightActiveGenerations(result.raw?.generation ?? null);

  // Map location — fetch grouped by gen, then build dynamic toggles
  const originGenNum = ORIGIN_GEN_NUM[
    (Array.isArray(result.raw?.generation)
      ? result.raw.generation[0]
      : result.raw?.generation ?? ''
    ).toLowerCase().trim()
  ] ?? null;
  _currentPokemonName = name;
  _currentEncountersByGen = await fetchLocationsByGen(poke.id);
  buildMapToggles(_currentEncountersByGen, originGenNum);

  // Similar Pokémon (same primary type)
  renderSimilarPokemon(poke.types[0], name);
}

// ─────────────────────────────────────────────────────────────
// 10. Photo card updater
// ─────────────────────────────────────────────────────────────
function updatePhotoCard(artworkUrl, name, pokeId, primaryType) {
  const img = document.getElementById('psprite');
  if (img) {
    // artworkUrl comes from pokemondb.net — NOT PokeAPI
    img.src = artworkUrl || `/images/${name.toLowerCase()}_image.jpg`;
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
