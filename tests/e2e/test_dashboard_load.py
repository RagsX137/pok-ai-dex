import pytest

pytestmark = pytest.mark.e2e


def test_dashboard_serves(live_url):
    import requests
    r = requests.get(f"{live_url}/dashboard", timeout=10)
    assert r.status_code == 200
    assert "atomic-search-interface" in r.text


def test_static_assets_and_images_serve(live_url):
    import requests
    assert requests.get(f"{live_url}/frontend/dashboard.css", timeout=10).status_code == 200
    assert requests.get(f"{live_url}/images/placeholder.png", timeout=10).status_code == 200


def test_classic_ui_still_serves(live_url):
    import requests
    r = requests.get(f"{live_url}/", timeout=10)
    assert r.status_code == 200
    assert "pokedex-device" in r.text


def test_default_load_populates_panels(dashboard):
    assert "Bulbasaur" in dashboard.locator("#rp-name").inner_text()
    assert dashboard.locator("#type-grid .tchip").count() == 18
    assert dashboard.locator("#gen-list .gen-item").count() == 9
    assert dashboard.locator("#stat-bars .srow2").count() == 6
    assert dashboard.locator("#weak-chips .echip").count() > 0
