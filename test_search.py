"""
Tests the Pokédex search box in the browser using Playwright.
Server must already be running on port 5003.

Uses the Coveo Atomic headless searchBox controller (sb.searchBox.updateText/submit)
to properly trigger searches, since the input lives inside a shadow root.
"""
from playwright.sync_api import sync_playwright
import time


def run_search(page, query):
    """Trigger a search via the Atomic headless searchBox controller."""
    result = page.evaluate("""
        (q) => {
            const sb = document.querySelector('atomic-search-box');
            if (!sb || !sb.searchBox) return 'NO SEARCHBOX CONTROLLER';
            sb.searchBox.updateText(q);
            sb.searchBox.submit();
            return 'ok';
        }
    """, query)
    return result


def get_engine_state(page):
    """Return search engine state dict: queryText, results_count, first_title, error."""
    return page.evaluate("""
        () => {
            const si = document.querySelector('atomic-search-interface');
            if (!si || !si.engine) return null;
            const s = si.engine.state.search;
            const q = si.engine.state.query;
            return {
                queryText:     q ? q.q : '',
                results_count: s ? s.results.length : 0,
                first_title:   s && s.results[0] ? s.results[0].title : '',
                is_loading:    s ? s.isLoading : false,
                error:         s ? (s.error ? s.error.message : null) : null,
                all_titles:    s ? s.results.map(r => r.title) : [],
            };
        }
    """)


def test_search(query, expected_fragment):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        console_logs = []
        errors = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: errors.append(str(err)))

        print(f"\n{'='*60}")
        print(f"TEST: '{query}' → expect '{expected_fragment}'")
        print(f"{'='*60}")

        page.goto("http://localhost:5003")
        page.wait_for_load_state("networkidle")
        time.sleep(4)

        ctrl_result = run_search(page, query)
        print(f"  Controller call: {ctrl_result}")
        time.sleep(4)

        state = get_engine_state(page)
        if state is None:
            print("  ❌ FAIL: No engine state available")
        else:
            print(f"  Query in engine: '{state['queryText']}'")
            print(f"  Results count:   {state['results_count']}")
            print(f"  Error:           {state['error']}")
            if state['all_titles']:
                print(f"  Top results:")
                for t in state['all_titles'][:5]:
                    print(f"    • {t}")

            found = any(expected_fragment.lower() in t.lower() for t in state['all_titles'])
            if found:
                print(f"  ✅ PASS: Found '{expected_fragment}' in results")
            else:
                print(f"  ❌ FAIL: '{expected_fragment}' not in results")

        if errors:
            print(f"  Page errors: {errors}")

        browser.close()


if __name__ == "__main__":
    test_cases = [
        ("pikachu",   "Pikachu"),
        ("charizard", "Charizard"),
        ("mewtwo",    "Mewtwo"),
        ("garchomp",  "Garchomp"),
        ("eevee",     "Eevee"),
        ("bulbasaur", "Bulbasaur"),
    ]

    passed = 0
    failed = 0
    for query, expected in test_cases:
        test_search(query, expected)

    print("\n" + "="*60)
    print("All tests complete.")
    print("="*60)
