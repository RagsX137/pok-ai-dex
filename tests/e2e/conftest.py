import pytest

# exc_type=ImportError (not the pytest-9 default of ModuleNotFoundError) so a
# broken Playwright install (e.g. a native-dependency/ABI mismatch, which
# raises a plain ImportError rather than ModuleNotFoundError) is also treated
# as "unavailable" and skipped here, rather than blowing up collection for
# the whole repo — tests/unit must survive Playwright being present but
# broken, not just Playwright being absent.
pytest.importorskip("playwright.sync_api", exc_type=ImportError)
from playwright.sync_api import sync_playwright  # noqa: E402


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def dashboard(browser, live_url):
    """A dashboard page that has finished its default Bulbasaur load."""
    page = browser.new_page()
    page.goto(f"{live_url}/dashboard")
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_function(
        "() => document.querySelector('#rp-name')?.textContent.trim() "
        "&& document.querySelector('#rp-name').textContent.trim() !== '—'",
        timeout=25000,
    )
    yield page
    page.close()


@pytest.fixture
def search(dashboard):
    def _search(query: str, expect: str | None = None, timeout: int = 20000):
        if expect:
            # Snapshot the tags before searching so we can wait for them to
            # change. selectResult() sets #rp-name at line 980 (before PokéAPI)
            # and #rp-tags + #weak-chips only after PokéAPI returns (lines
            # 1017/1020). PokéAPI results are cached in a JS Map, so re-queries
            # resolve synchronously — networkidle fires before the DOM update.
            # Waiting for #rp-tags to differ from the pre-search snapshot is the
            # reliable "full panel rendered" signal that guarantees #weak-chips
            # is also up to date for the new Pokémon.
            prev_tags = dashboard.locator("#rp-tags").inner_html()

        dashboard.fill("#search-input", query)
        dashboard.press("#search-input", "Enter")

        if expect:
            dashboard.wait_for_function(
                "([name, prev]) => {"
                "  const rp = document.querySelector('#rp-name')?.textContent ?? '';"
                "  const tags = document.querySelector('#rp-tags')?.innerHTML ?? '';"
                "  return rp.includes(name) && tags !== prev;"
                "}",
                arg=[expect, prev_tags], timeout=timeout,
            )
        else:
            dashboard.wait_for_load_state("networkidle", timeout=timeout)
        return dashboard
    return _search
