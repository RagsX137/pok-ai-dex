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
        dashboard.fill("#search-input", query)
        dashboard.press("#search-input", "Enter")

        if expect:
            # Wait for #rp-tags to be NON-EMPTY, not merely different.
            # selectResult() calls setPanelHeader(name, [], null) synchronously
            # before awaiting PokéAPI (dashboard.js:840), which sets #rp-name and
            # BLANKS #rp-tags on every search. A "tags changed" predicate is
            # therefore satisfied ~0.27s in, while #weak-chips still holds the
            # previous Pokemon's chips — the tests then asserted against stale
            # data. Only the post-await setPanelHeader(name, poke.types, id)
            # refills #rp-tags, and renderTypeEffectiveness() runs in that same
            # synchronous block, so non-empty tags guarantee fresh #weak-chips.
            dashboard.wait_for_function(
                "(name) => {"
                "  const rp = document.querySelector('#rp-name')?.textContent ?? '';"
                "  const tags = document.querySelector('#rp-tags')?.innerHTML ?? '';"
                "  return rp.includes(name) && tags.trim() !== '';"
                "}",
                arg=expect, timeout=timeout,
            )
        else:
            dashboard.wait_for_load_state("networkidle", timeout=timeout)
        return dashboard
    return _search
