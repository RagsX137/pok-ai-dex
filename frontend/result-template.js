import { TYPE_COLORS } from './type-colors.js';

/**
 * Build the inner HTML for a single Pokémon result row rendered inside
 * the dark Pokédex screen. Used by the Atomic result template.
 *
 * @param {object} result - Coveo result object
 * @returns {string} HTML string
 */
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
      <img src="${imgSrc}" width="40" height="40"
           style="object-fit:contain;flex-shrink:0;"
           onerror="this.src='/images/placeholder.png'" />
      <div style="flex:1;min-width:0;">
        <div style="font-size:12px;font-weight:700;color:#f0d040;
                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
          ${name}
        </div>
        <div style="font-size:10px;color:rgba(240,208,64,0.55);">
          #${num} &middot; Total ${total}
        </div>
      </div>
      <div style="display:flex;gap:3px;flex-shrink:0;">
        <span style="background:${c1.bg};color:${c1.text};font-size:9px;font-weight:700;
                     padding:2px 5px;border-radius:3px;">${type1}</span>
        ${c2 ? `<span style="background:${c2.bg};color:${c2.text};font-size:9px;
                              font-weight:700;padding:2px 5px;border-radius:3px;">${type2}</span>` : ''}
      </div>
    </div>
  `;
}
