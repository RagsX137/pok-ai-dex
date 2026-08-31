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
  if (tagsEl) {
    tagsEl.innerHTML = types.length
      ? types.map(t => {
          const colors = TYPE_COLORS[t.toLowerCase()] ?? { bg: '#444', text: '#ccc' };
          return `<span class="rptag" style="background:${colors.bg}33;color:${colors.bg}">${t.charAt(0).toUpperCase() + t.slice(1)}</span>`;
        }).join('') + (pokeId ? `<span class="rptag" style="background:rgba(79,195,247,.15);color:#4fc3f7">#${String(pokeId).padStart(3,'0')}</span>` : '')
      : '';
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
