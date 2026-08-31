# Known Issues

Documented defects that have been observed and recorded as strict xfails in the
test suite. Each entry describes the wrong behaviour, the correct behaviour, and
which test marks it.

---

## MAP-001: Map pan has zero effect in headless/small viewports

**Test:** `tests/e2e/test_filters_and_map.py::test_map_pan_updates_data_pan_x`
**Status:** `xfail(strict=True)`

**Wrong behaviour:** Dragging the map region image does not change `data-pan-x`.
The `wireMapPan` `panTo()` function clamps the displacement to
`[-overX, +overX]` where `overX = max(0, imgWidth - containerWidth) / 2`. In a
headless Playwright viewport the map image renders at the same CSS size as its
container (no visual overflow), so `overX = 0` and `clamp(40, 0, 0) = 0` —
every drag is clamped to zero.

**Correct behaviour:** In a large enough browser window the image overflows the
container (CSS renders it at 180% width), `overX > 0`, and dragging 40 px moves
`data-pan-x` by the clamped displacement.

**Fix:** Either set a larger Playwright viewport (`width: 1600, height: 900`) in
the `browser` fixture, or add a minimum rendered width to the map container so
it always has measurable overflow. Do not change the pan logic itself.

---

## BUG-001: Pokéapi 404s for synthetic Coveo-index titles

**Status:** Informational only — no test asserts this.

The live Coveo index returns some listing-page results (e.g. "Pokémon Shiny-dex
compilation") as top results for certain queries. `fetchPokeData` normalises
these titles through `extractPokemonName` and calls PokéAPI, which returns 404.
The dashboard handles the 404 gracefully (blanks the panel) but each
unresolvable title emits a 404 error in the browser network tab. This is
third-party data quality, predates this reorganisation, and is not a regression.

---
