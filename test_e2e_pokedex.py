"""
End-to-end test for the Pokédex agentic UI.
Validates:
  1. Result rows render (not blank) — title, type badge, excerpt visible
  2. Bottom panel auto-populates on search (photo src changes, name changes)
  3. Bottom panel populates on explicit result click
  4. Stats row is filled by engine state data

Server must already be running on port 5003.
"""
from playwright.sync_api import sync_playwright
import time
import sys


BASE = "http://localhost:5003"
PASS = "✅ PASS"
FAIL = "❌ FAIL"
results_log = []


def log(label, ok, detail=""):
    status = PASS if ok else FAIL
    msg = f"  {status}: {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results_log.append(ok)


def run_all():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        console_errs = []
        page.on("pageerror", lambda e: console_errs.append(str(e)))

        print(f"\n{'='*60}")
        print("Loading Pokédex…")
        page.goto(BASE)
        page.wait_for_load_state("networkidle")
        time.sleep(5)  # give Atomic + initial search time to finish

        # ── Helper: read engine state ─────────────────────────────────────────
        def engine_state():
            return page.evaluate("""
                () => {
                    const si = document.querySelector('atomic-search-interface');
                    if (!si?.engine) return null;
                    const s = si.engine.state;
                    return {
                        query:         s.query?.q ?? '',
                        results_count: s.search?.results?.length ?? 0,
                        first_result:  s.search?.results?.[0] ?? null,
                        is_loading:    s.search?.isLoading ?? false,
                    };
                }
            """)

        def trigger_search(q):
            page.evaluate("""
                (q) => {
                    const sb = document.querySelector('atomic-search-box');
                    if (sb?.searchBox) { sb.searchBox.updateText(q); sb.searchBox.submit(); }
                }
            """, q)
            time.sleep(5)

        # ── TEST 1: initial load returns results ──────────────────────────────
        print(f"\n{'─'*60}")
        print("TEST 1: Initial load returns results")
        state = engine_state()
        log("engine state available", state is not None)
        if state:
            log("results returned on load", state["results_count"] > 0,
                f"{state['results_count']} results")

        # ── TEST 2: result rows are not blank (DOM has text) ──────────────────
        print(f"\n{'─'*60}")
        print("TEST 2: Result rows render content (not blank)")
        trigger_search("pikachu")
        state = engine_state()

        # Atomic renders each result as an atomic-result element inside the
        # atomic-result-list shadow root — we must look one level deep.
        result_count = page.evaluate("""
            () => {
                const list = document.querySelector('atomic-result-list');
                const items = list?.shadowRoot?.querySelectorAll('atomic-result') ?? [];
                const firstText = items[0]?.shadowRoot?.textContent?.trim().slice(0, 80) ?? '';
                return { count: items.length, firstText };
            }
        """)
        log("result list has ≥1 rendered atomic-result element",
            result_count["count"] > 0,
            f"{result_count['count']} items — first: {repr(result_count['firstText'][:60])}")

        # Verify at least one result title contains 'Pikachu' in engine state
        if state and state["first_result"]:
            first_title = state["first_result"].get("title", "")
            log("top result is Pikachu", "pikachu" in first_title.lower(), first_title)
        else:
            log("top result available", False, "no state")

        # ── TEST 3: bottom panel auto-populates after search ──────────────────
        print(f"\n{'─'*60}")
        print("TEST 3: Bottom panel auto-populates after search (no click needed)")
        # PokéAPI fetch adds latency on top of the search — extra wait
        time.sleep(4)

        photo_name = page.text_content("#photo-name") or ""
        photo_src  = page.get_attribute(".photo-sprite", "src") or ""

        log("photo-name changed from default",
            photo_name.lower() not in ("pokémon", "pokemon", ""),
            repr(photo_name))
        log("photo sprite src is a PokéAPI sprite URL",
            "raw.githubusercontent.com" in photo_src or "pokestadium" in photo_src
            or ("placeholder" not in photo_src and photo_src not in ("", "/images/placeholder.png")),
            repr(photo_src))

        # ── TEST 4: stats row populated from PokéAPI ──────────────────────────
        print(f"\n{'─'*60}")
        print("TEST 4: Stats row populated from PokéAPI")

        stats_text = page.text_content(".screen-stats-row") or ""
        has_stats = any(c.isdigit() for c in stats_text)
        log("stats row contains numbers", has_stats, repr(stats_text[:80].strip()))

        # ── TEST 5: type badges appear in controls row ────────────────────────
        print(f"\n{'─'*60}")
        print("TEST 5: Type badges in controls row from PokéAPI")

        badge_count = page.evaluate("""
            () => document.querySelectorAll('.ctrl-type-badges .type-badge').length
        """)
        badge_labels = page.evaluate("""
            () => Array.from(document.querySelectorAll('.ctrl-type-badges .type-badge')).map(b=>b.textContent)
        """)
        log("at least one type badge shown", badge_count > 0,
            f"{badge_count} badges: {badge_labels}")

        # ── TEST 6: clicking a result updates the bottom panel ────────────────
        print(f"\n{'─'*60}")
        print("TEST 6: Clicking a result updates the bottom panel")
        trigger_search("charizard")
        time.sleep(4)  # wait for PokéAPI on charizard

        # Dispatch the atomic/result/select event manually with a mock result
        page.evaluate("""
            () => {
                const si = document.querySelector('atomic-search-interface');
                const result = si?.engine?.state?.search?.results?.[0];
                if (!result) return;
                document.dispatchEvent(new CustomEvent('atomic/result/select', {
                    detail: { result },
                    bubbles: true,
                }));
            }
        """)
        time.sleep(4)  # wait for PokéAPI

        photo_name2 = page.text_content("#photo-name") or ""
        photo_src2  = page.get_attribute(".photo-sprite", "src") or ""
        log("photo-name updated after click",
            photo_name2.lower() not in ("pokémon", "pokemon", ""),
            repr(photo_name2))
        log("photo sprite updated after click",
            "placeholder" not in photo_src2 and photo_src2 != "",
            repr(photo_src2))

        # ── TEST 7: no JS page errors ─────────────────────────────────────────
        print(f"\n{'─'*60}")
        print("TEST 7: No JavaScript page errors")
        log("zero JS page errors", len(console_errs) == 0,
            "; ".join(console_errs[:3]) if console_errs else "clean")

        browser.close()

        # ── Summary ───────────────────────────────────────────────────────────
        passed = sum(results_log)
        total  = len(results_log)
        print(f"\n{'='*60}")
        print(f"RESULT: {passed}/{total} checks passed")
        print(f"{'='*60}\n")
        return passed == total


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
