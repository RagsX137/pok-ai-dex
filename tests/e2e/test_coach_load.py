# tests/e2e/test_coach_load.py
import pytest

pytestmark = pytest.mark.e2e


def test_coach_page_serves(live_url):
    import requests
    r = requests.get(f"{live_url}/coach", timeout=10)
    assert r.status_code == 200
    assert "Professor Oak" in r.text
    assert "{{ COVEO_ORGANIZATION_ID }}" not in r.text


def test_coach_css_serves(live_url):
    import requests
    assert requests.get(f"{live_url}/frontend/coach.css", timeout=10).status_code == 200


def test_coach_quick_chips_visible(browser, live_url):
    page = browser.new_page()
    page.goto(f"{live_url}/coach")
    page.wait_for_load_state("networkidle", timeout=15000)
    chips = page.locator(".quick-chip")
    assert chips.count() >= 3
    page.close()


def test_coach_single_turn(browser, live_url):
    """Submit a simple question and confirm an Oak bubble appears."""
    page = browser.new_page()
    page.goto(f"{live_url}/coach")
    page.wait_for_load_state("networkidle", timeout=15000)
    page.fill("#coach-input", "Tell me about Pikachu")
    page.press("#coach-input", "Enter")
    # Wait for Oak bubble to appear (the thinking indicator is replaced)
    page.wait_for_selector(".bubble-oak", timeout=30000)
    assert page.locator(".bubble-oak").count() >= 1
    page.close()


def test_coach_comparison_url_param(browser, live_url):
    """?compare=charizard&with=dragonite should auto-render a comparison panel."""
    page = browser.new_page()
    page.goto(f"{live_url}/coach?compare=charizard&with=dragonite", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=15000)
    # Wait for at least one comparison card
    page.wait_for_selector(".cmp-card", timeout=35000)
    assert page.locator(".cmp-card").count() == 2
    page.close()


def test_coach_compare_button_on_dashboard(browser, live_url):
    """Hovering a result row on the dashboard shows a ⇌ button."""
    page = browser.new_page()
    page.goto(f"{live_url}/dashboard")
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_function(
        "() => document.querySelector('#rp-name')?.textContent.trim() !== '—'",
        timeout=25000,
    )
    # Search for Charizard so there are result rows
    page.fill("#search-input", "charizard")
    page.press("#search-input", "Enter")
    page.wait_for_load_state("networkidle", timeout=15000)
    first_row = page.locator(".ritem").first
    first_row.hover()
    cmp_btn = first_row.locator(".cmp-btn")
    assert cmp_btn.is_visible(timeout=3000)
    page.close()
