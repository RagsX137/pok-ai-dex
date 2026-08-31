import re
from pathlib import Path

from pokedex.config import settings
from eval_harness.typechart import TYPES, TypeChart

JS = settings.repo_root / "frontend" / "modules" / "type-chart.js"


def _parse_js_chart() -> dict[str, dict[str, float]]:
    """Read the sparse TYPE_CHART object literal out of the ES module."""
    src = JS.read_text()
    body = src.split("const TYPE_CHART = {", 1)[1].split("\n};", 1)[0]
    chart: dict[str, dict[str, float]] = {}
    for line in body.splitlines():
        m = re.match(r"\s*(\w+):\s*\{(.*)\},?\s*$", line)
        if not m:
            continue
        atk, pairs = m.group(1), m.group(2)
        chart[atk] = {
            k: float(v)
            for k, v in re.findall(r"(\w+)\s*:\s*([\d.]+)", pairs)
        }
    return chart


def test_js_and_python_cover_the_same_18_types():
    js = _parse_js_chart()
    assert set(js) == set(TYPES)


def test_js_chart_matches_python_chart():
    js = _parse_js_chart()
    mismatches = []
    for atk in TYPES:
        for dfn in TYPES:
            js_mult = js[atk].get(dfn, 1.0)
            py_mult = TypeChart.effectiveness(atk, [dfn])
            if js_mult != py_mult:
                mismatches.append(f"{atk} -> {dfn}: js={js_mult} py={py_mult}")
    assert not mismatches, "\n".join(mismatches)
