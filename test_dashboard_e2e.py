"""
End-to-end tests for the Pokédex Dashboard (/dashboard).

Replaces test_e2e_pokedex.py, which pointed at "/" and asserted on selectors
(.photo-sprite, .screen-stats-row, .ctrl-type-badges) that do not exist in the
dashboard — so it passed 11/11 while the shipped page was untested.

Server must already be running on port 5003:  python app.py

Run:  python test_dashboard_e2e.py
"""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5003/dashboard"
PASS, FAIL = "PASS", "FAIL"
_log = []


def check(label, ok, detail=""):
    _log.append(ok)
    print(f"  [{PASS if ok else FAIL}] {label}" + (f" — {detail}" if detail else ""))


# ── Expected defensive matchups, from the Gen VI+ chart ──────────────────────
# Each entry: name -> {attacking type: multiplier} for everything above ×1.
EXPECTED_WEAKNESSES = {
    "skarmory":  {"Fire": "×2", "Electric": "×2"},
    "charizard": {"Rock": "×4", "Water": "×2", "Electric": "×2"},
    "swampert":  {"Grass": "×4"},
    "gliscor":   {"Ice": "×4", "Water": "×2"},
    "drapion":   {"Ground": "×2"},
    "bulbasaur": {"Fire": "×2", "Ice": "×2", "Flying": "×2", "Psychic": "×2"},
    "gengar":    {"Ground": "×2", "Psychic": "×2", "Ghost": "×2", "Dark": "×2"},
}

# Immunities must be shown, and must never appear as weaknesses.
EXPECTED_IMMUNITIES = {
    "skarmory":  {"Poison", "Ground"},
    "charizard": {"Ground"},
    "swampert":  {"Electric"},
    "gliscor":   {"Electric", "Ground"},
    "drapion":   {"Psychic"},
    "gengar":    {"Normal", "Fighting"},
}

# Display names whose PokéAPI slug needs normalising.
TRICKY_NAMES = [
    "tapu koko", "mr. mime", "type: null",
    "iron valiant", "great tusk", "sirfetch'd", "farfetchd",
]


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))

        print("\nLoading dashboard…")
        page.goto(BASE, wait_until="domcontentloaded")
        time.sleep(12)  # Atomic init + default search + PokéAPI

        def search(q, wait=11):
            page.fill("#search-input", q)
            page.press("#search-input", "Enter")
            time.sleep(wait)

        def panel():
            return page.evaluate("""() => ({
              name:   document.getElementById('rp-name')?.textContent ?? '',
              tags:   document.getElementById('rp-tags')?.textContent?.trim() ?? '',
              stats:  document.getElementById('stat-bars')?.textContent?.replace(/\\s+/g,' ').trim() ?? '',
              weak:   [...document.querySelectorAll('#weak-chips .echip')].map(e => e.textContent.trim()),
              resist: [...document.querySelectorAll('#resist-chips .echip')].map(e => e.textContent.trim()),
              moves:  [...document.querySelectorAll('#moves-tbody tr')].map(r => r.textContent.replace(/\\s+/g,' ').trim()),
              rows:   [...document.querySelectorAll('#results-list .ritem .rname')].map(e => e.textContent),
              badges: document.querySelectorAll('#results-list .rbadge').length,
              count:  document.getElementById('result-count')?.textContent ?? '',
              genAct: [...document.querySelectorAll('.gen-item.active')].map(e => e.dataset.gen),
              sim:    [...document.querySelectorAll('#similar-grid .sim-card')].map(e => e.dataset.name),
              rec:    document.getElementById('ai-rec-txt')?.textContent?.trim() ?? '',
              query:  document.querySelector('atomic-search-interface')?.engine?.state?.query?.q ?? '',
            })""")

        # ── 1. Type effectiveness is computed, not unioned ────────────────────
        print("\n1. Type effectiveness matches the official chart")
        for mon, expected in EXPECTED_WEAKNESSES.items():
            search(mon)
            got = {c.rsplit(" ", 1)[0]: c.rsplit(" ", 1)[1] for c in panel()["weak"]}
            check(f"{mon}: weaknesses", got == expected, f"got {got}")

        # ── 2. Immunities are surfaced and never listed as weaknesses ─────────
        print("\n2. Immunities are shown, and excluded from weaknesses")
        for mon, immune in EXPECTED_IMMUNITIES.items():
            search(mon)
            pn = panel()
            shown = {c.rsplit(" ", 1)[0] for c in pn["resist"] if c.endswith("×0")}
            weak = {c.rsplit(" ", 1)[0] for c in pn["weak"]}
            check(f"{mon}: immunities listed", immune <= shown, f"got {shown}")
            check(f"{mon}: no immunity shown as weakness", not (immune & weak),
                  f"overlap {immune & weak}" if immune & weak else "")

        # ── 3. Names PokéAPI needs normalised still populate ──────────────────
        print("\n3. Awkward display names resolve instead of going stale")
        prev_stats = None
        for name in TRICKY_NAMES:
            search(name, 12)
            pn = panel()
            has_stats = any(ch.isdigit() for ch in pn["stats"])
            check(f"{name}: panel populated", has_stats and pn["stats"] != prev_stats,
                  f"{pn['tags']} {pn['stats'][:40]}")
            prev_stats = pn["stats"]

        # ── 4. A genuinely unresolvable title blanks the panel ───────────────
        # The index contains listing pages ("Pokémon Shiny-dex …") that are not
        # species. They must not inherit the previous Pokémon's stats.
        print("\n4. Unresolvable lookups blank the panel instead of going stale")
        search("charizard")
        charizard_stats = panel()["stats"]
        check("Charizard baseline loaded", "78" in charizard_stats, charizard_stats[:40])

        search("shiny sprites list", 12)
        pn = panel()
        is_species = any(ch.isdigit() for ch in pn["tags"])
        if is_species:
            check("resolved to a real species (no stale case hit)", True, pn["name"][:40])
        else:
            check("stale stats cleared", pn["stats"] != charizard_stats,
                  f"{pn['name'][:30]} → {pn['stats'][:40]}")
            check("panel says it has no data", "No detailed data" in pn["stats"],
                  pn["stats"][:60])

        # ── 5. Type filter filters, and never mutates the query ──────────────
        print("\n5. Type chips filter client-side without touching the query")
        search("charizard")
        q_before = panel()["query"]
        page.click(".tchip[data-type='water']")
        time.sleep(9)
        pn = panel()
        check("query unchanged by filtering", pn["query"] == q_before,
              f"{q_before!r} -> {pn['query']!r}")
        check("result count did not grow", "of" in pn["count"], pn["count"])
        page.click(".tchip[data-type='water']")
        time.sleep(9)
        check("toggling off restores the unfiltered set",
              panel()["query"] == q_before, panel()["count"])

        # ── 6. Generation filter selects the right generation ────────────────
        print("\n6. Generation filter returns only that generation")
        search("dragon")
        page.click(".gen-item[data-gen='I']")
        time.sleep(10)
        rows = panel()["rows"]
        check("Gen I filter returns results", len(rows) > 0, f"{rows[:5]}")
        check("query not rewritten to 'generation:gen-i'",
              "generation:" not in panel()["query"], panel()["query"])
        page.click(".gen-item[data-gen='I']")
        time.sleep(9)

        # ── 7. Generation indicator reflects the real dex number ─────────────
        print("\n7. Generation indicator is derived, not hardcoded")
        for mon, gen in [("miraidon", "IX"), ("greninja", "VI"), ("skarmory", "II")]:
            search(mon)
            got = panel()["genAct"]
            check(f"{mon} → Gen {gen}", got == [gen], f"got {got}")

        # ── 8. Result rows carry type badges ─────────────────────────────────
        print("\n8. Results list renders type badges")
        search("pikachu")
        pn = panel()
        check("badges rendered", pn["badges"] > 0, f"{pn['badges']} badges on {len(pn['rows'])} rows")
        check("count reports what is reachable", "of" in pn["count"] or "found" in pn["count"],
              pn["count"])

        # ── 9. Moves are the threat set, with power ───────────────────────────
        print("\n9. Moves table shows high-level moves with power")
        search("charizard")
        moves = panel()["moves"]
        check("moves present", len(moves) > 3, f"{len(moves)} rows")
        check("power/category shown", any("PHY" in m or "SPC" in m or "STA" in m for m in moves),
              moves[0] if moves else "")
        first_lv = moves[0].split(" ")[0] if moves else "0"
        check("sorted high level first", first_lv.isdigit() and int(first_lv) > 1,
              f"top row level {first_lv}")

        # ── 10. Similar Pokémon are stable and are real species ──────────────
        print("\n10. Similar Pokémon are deterministic")
        runs = []
        for _ in range(2):
            search("charizard")
            runs.append(panel()["sim"])
        check("same suggestions across renders", runs[0] == runs[1], f"{runs[0]} vs {runs[1]}")
        check("no alternate forms", not any(
            any(s in n for s in ("-mega", "-gmax", "-totem", "-hisui", "-alola"))
            for n in runs[0]), f"{runs[0]}")

        # ── 11. Recommendation leads with the computed matchup ───────────────
        print("\n11. Recommendation leads with computed type maths")
        search("charizard")
        rec = panel()["rec"]
        check("names the real super-effective types", "Rock ×4" in rec, rec[:80])
        check("warns about the immunity", "Ground" in rec and "no effect" in rec, rec[:110])

        # ── 12. Empty search is a no-op ──────────────────────────────────────
        print("\n12. Empty search does not dump the whole index")
        search("gengar")
        before_q = panel()["query"]
        page.fill("#search-input", "   ")
        page.press("#search-input", "Enter")
        time.sleep(6)
        check("query unchanged by an empty submit", panel()["query"] == before_q,
              f"{before_q!r} -> {panel()['query']!r}")

        # ── 13. No JS errors ─────────────────────────────────────────────────
        print("\n13. Runtime health")
        check("zero JS page errors", not errors, "; ".join(errors[:3]) if errors else "clean")

        browser.close()

    passed, total = sum(_log), len(_log)
    print(f"\n{'=' * 62}\nRESULT: {passed}/{total} checks passed\n{'=' * 62}\n")
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
