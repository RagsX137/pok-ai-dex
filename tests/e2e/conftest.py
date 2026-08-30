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
