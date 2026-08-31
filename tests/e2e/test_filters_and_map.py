import pytest

pytestmark = pytest.mark.e2e


def test_type_chip_toggles_on_and_off(search):
    """Type filter chip turns 'on' on first click and back off on second."""
    page = search("Pikachu", expect="Pikachu")
    elec_chip = page.locator(".tchip[data-type='electric']")
    elec_chip.click()
    page.wait_for_timeout(1000)
    assert "on" in (elec_chip.get_attribute("class") or "")

    elec_chip.click()
    page.wait_for_timeout(1000)
    assert "on" not in (elec_chip.get_attribute("class") or "")


def test_generation_row_toggles_on(search):
    """Gen II row gets the 'on' class when clicked."""
    page = search("Pikachu", expect="Pikachu")
    gen_ii = page.locator(".gen-item[data-gen='II']")
    gen_ii.click()
    page.wait_for_timeout(3000)
    assert "on" in (gen_ii.get_attribute("class") or "")
    # Clean up
    gen_ii.click()
    page.wait_for_timeout(1000)


def test_map_gen_toggles_are_mutually_exclusive(search):
    """Only one map gen toggle can be active at a time."""
    page = search("Pidgey", expect="Pidgey")
    # Wait for encounter data to load
    page.wait_for_selector(".gtbtn", timeout=20000)
    toggles = page.locator(".gtbtn")
    if toggles.count() < 2:
        pytest.skip("Pidgey returned fewer than 2 region toggles")

    # Click the second toggle — the first was already active by default
    toggles.nth(1).click()
    page.wait_for_timeout(1000)
    assert page.locator(".gtbtn.on").count() == 1


@pytest.mark.xfail(
    reason=(
        "Map pan is clamped to the image overflow area. In a headless viewport "
        "the map image renders at the same size as its container (overflow=0), "
        "so clamp(40, 0, 0)=0 and data-pan-x never changes. See docs/known-issues.md."
    ),
    strict=True,
)
def test_map_pan_updates_data_pan_x(search):
    """Dragging the map image changes its data-pan-x attribute."""
    page = search("Pidgey", expect="Pidgey")
    page.wait_for_selector("#map-region-wrap", timeout=20000)
    wrap = page.locator("#map-region-wrap")
    if not wrap.is_visible():
        pytest.skip("map region wrap not visible — no encounter data")
    box = wrap.bounding_box()
    if box is None:
        pytest.skip("map wrap has no bounding box")

    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 40, cy + 20)
    page.mouse.up()
    page.wait_for_timeout(500)

    pan_x = page.locator("#map-region-img").get_attribute("data-pan-x")
    assert pan_x is not None and float(pan_x) != 0
